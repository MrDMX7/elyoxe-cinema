// elyoxe-cinema-moved — viewer-request on the /cinema* and /en/cinema* behaviors of the elyoxe.com
// distribution (E2QY4WECG1P5WO). «سينما» moved to its own host; every old URL answers 301 with the
// same path (and query string) there:
//   /cinema           → https://cinema.elyoxe.com/
//   /cinema/x/y/      → https://cinema.elyoxe.com/x/y/
//   /en/cinema/x      → https://cinema.elyoxe.com/en/x
// Anything else these patterns happen to catch (/cinemas, /cinema-foo) is passed through untouched.
var HOST = 'https://cinema.elyoxe.com';

function query(qs) {
    var parts = [];
    var keys = Object.keys(qs);
    for (var i = 0; i < keys.length; i++) {
        var k = keys[i], v = qs[k];
        if (v.multiValue) {
            for (var j = 0; j < v.multiValue.length; j++) parts.push(k + '=' + v.multiValue[j].value);
        } else {
            parts.push(v.value === '' ? k : k + '=' + v.value);
        }
    }
    return parts.length ? '?' + parts.join('&') : '';
}

function target(uri) {
    if (uri === '/cinema' || uri.indexOf('/cinema/') === 0) return uri.slice(7) || '/';
    if (uri === '/en/cinema' || uri.indexOf('/en/cinema/') === 0) return '/en' + (uri.slice(10) || '/');
    return null;
}

function handler(event) {
    var request = event.request;
    var path = target(request.uri);
    if (path === null) return request;
    return {
        statusCode: 301,
        statusDescription: 'Moved Permanently',
        headers: {
            location: { value: HOST + path + query(request.querystring) },
            'cache-control': { value: 'public, max-age=86400' }
        }
    };
}
