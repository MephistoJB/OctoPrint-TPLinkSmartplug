"""Safe error conversion, importable even by legacy Python installations."""
def safe_tapo_error(error, python_version):
    if python_version < (3, 11):
        return "Tapo support requires Python 3.11 or newer."
    from .tapo_transport import TapoError
    if isinstance(error, TapoError):
        return str(error)
    return "Tapo support could not be loaded. Check the plugin dependencies."
