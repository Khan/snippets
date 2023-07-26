#!/usr/bin/env python3

import snippets

import google.appengine.api
import google.cloud.ndb


class NDBMiddleware:
    """WSGI middleware to wrap the app in Google Cloud NDB context"""
    def __init__(self, app):
        self.app = app
        self.client = google.cloud.ndb.Client()

    def __call__(self, environ, start_response):
        with self.client.context():
            return self.app(environ, start_response)

app = snippets.app
app.wsgi_app = google.appengine.api.wrap_wsgi_app(app.wsgi_app)
app.wsgi_app = NDBMiddleware(app.wsgi_app)


if __name__ == '__main__':
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. You
    # can configure startup instructions by adding `entrypoint` to app.yaml.
    #
    # To control listening IP and port, set SERVER_NAME in the environment.
    # e.g. SERVER_NAME=127.0.0.1:8080
    # Default is to listen on 127.0.0.1:5000
    app.run(debug=True)
