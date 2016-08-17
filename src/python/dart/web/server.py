from dart.web import app


if __name__ == '__main__':
    context = (app.config['auth'].get('ssl_cert_path'), app.config['auth'].get('ssl_key_path'))
    app.run(host=app.config['dart_host'], port=app.config['dart_port'], use_reloader=False, ssl_context=context)
