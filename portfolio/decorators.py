from functools import wraps
from flask import session, redirect, url_for, request


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if kwargs.get("user_id") is None and not session.get("logged_in"):
            # User is not authenticated, redirect to login page
            return redirect(url_for("login", next=request.path))
        # User is authenticated, call the route function
        return f(*args, **kwargs)

    return wrapper
