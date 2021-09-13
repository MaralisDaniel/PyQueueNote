def get_debugger(debug_mode=False):
    if debug_mode:
        return print
    else:
        return lambda x: True
