#!/usr/bin/env python3

import snippets

from google.cloud import ndb


app = snippets.app


class NDBMiddleware:
    """WSGI middleware to wrap the app in Google Cloud NDB context"""
    def __init__(self, app):
        self.app = app
        self.client = ndb.Client()

    def __call__(self, environ, start_response):
        with self.client.context():
            return self.app(environ, start_response)

app.wsgi_app = NDBMiddleware(app.wsgi_app)


if __name__ == '__main__':
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. You
    # can configure startup instructions by adding `entrypoint` to app.yaml.
    app.run(host='127.0.0.1', debug=True)
