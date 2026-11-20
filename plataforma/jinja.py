from django.contrib import messages
from django.contrib.messages import get_messages
from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment


def _url_for(endpoint, **values):
    if endpoint == "static":
        filename = values.get("filename", "")
        if filename.lower() == "images/logo.png":
            filename = "images/Logo.png"
        return static(filename)
    return reverse(endpoint, kwargs=values or None)


def environment(**options):
    env = Environment(**options)
    env.globals.update(url_for=_url_for)
    return env
