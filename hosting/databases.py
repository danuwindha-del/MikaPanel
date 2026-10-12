import base64
import hashlib
import re
from contextlib import contextmanager
from cryptography.fernet import Fernet
import pymysql
from django.conf import settings
from django.db.models import F
from django.db import transaction
from .models import Account, ManagedDatabase


def encrypt_password(value):
    cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))
    return cipher.encrypt(value.encode()).decode()


def decrypt_password(value):
    cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))
    return cipher.decrypt(value.encode()).decode()


def identifiers(database):
    expected_db = "mika_" + database.account.id.hex[:12] + "_" + database.label
    expected_user = "mu" + database.id.hex[:16]
    if database.database_name != expected_db or database.username != expected_user or not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", database.label):
        raise ValueError("Invalid managed database identity")
    return expected_db, expected_user


@contextmanager
def root_connection():
    connection = pymysql.connect(unix_socket=settings.MIKA_MYSQL_SOCKET, user="root", autocommit=True, connect_timeout=5)
    try:
        yield connection
    finally:
        connection.close()


def provision(database, action):
    name, username = identifiers(database)
    if settings.MIKA_PROVISION_MODE != "demo":
        if not settings.MIKA_MYSQL_ENABLED:
            raise ValueError("MariaDB service is disabled")
        with root_connection() as connection, connection.cursor() as cursor:
            if action == "db_create":
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                cursor.execute("CREATE USER IF NOT EXISTS %s@'localhost' IDENTIFIED BY %s", (username, decrypt_password(database.password_ciphertext)))
                cursor.execute("ALTER USER %s@'localhost' IDENTIFIED BY %s", (username, decrypt_password(database.password_ciphertext)))
                # MySQL treats '_' as a wildcard in database-level grants, even in backticks.
                grant_name = name.replace("_", "\\_")
                cursor.execute(f"GRANT ALL PRIVILEGES ON `{grant_name}`.* TO %s@'localhost'", (username,))
            elif action == "db_rotate":
                cursor.execute("ALTER USER %s@'localhost' IDENTIFIED BY %s", (username, decrypt_password(database.password_ciphertext)))
            elif action == "db_delete":
                cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
                cursor.execute("DROP USER IF EXISTS %s@'localhost'", (username,))
            else:
                raise ValueError("Invalid database action")
    if action == "db_delete":
        with transaction.atomic():
            current = ManagedDatabase.objects.select_for_update().get(pk=database.pk)
            if current.state != "deleted":
                Account.objects.filter(pk=database.account_id, database_count__gt=0).update(database_count=F("database_count") - 1)
            ManagedDatabase.objects.filter(pk=database.pk).update(state="deleted", password_ciphertext="")
    else:
        ManagedDatabase.objects.filter(pk=database.pk).update(state="active" if settings.MIKA_PROVISION_MODE == "system" else "demo")
