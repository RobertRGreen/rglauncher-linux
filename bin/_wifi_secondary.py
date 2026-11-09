"""Optional camera-radio integration is not configured in the public edition."""
def _unavailable(*args, **kwargs):
    raise RuntimeError("A secondary camera-radio integration has not been configured")
def profiles():
    return {}
status = networks = connect = disconnect = forget = request = _unavailable
