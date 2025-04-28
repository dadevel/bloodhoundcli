# reenable md4
import ctypes
ctypes.CDLL('libssl.so').OSSL_PROVIDER_load(None, b'legacy')
ctypes.CDLL('libssl.so').OSSL_PROVIDER_load(None, b'default')
import hashlib


def nthash(value: str) -> str:
    hash = hashlib.new('md4')
    hash.update(value.encode('utf-16le'))
    return hash.hexdigest()


def md5(value: str) -> str:
    hash = hashlib.new('md5')
    hash.update(value.encode('utf8'))
    return hash.hexdigest()
