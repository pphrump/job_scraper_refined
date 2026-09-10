import bleach

def sanitize_input(input_str):
    return bleach.clean(input_str)