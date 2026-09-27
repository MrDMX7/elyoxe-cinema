// elyoxe-cinema-geo — viewer-request on the /geo behavior of the cinema distribution (E1200YJEC3LL6I).
// Answers the request itself (it never reaches the bucket) with the visitor's city among our eight, read
// from CloudFront's own geolocation of the viewer's address:
//   {"city": "al-ain"}   or   {"city": null}   (outside the UAE, or a city/region we cannot place)
// The CloudFront-Viewer-* headers reach a viewer-request function only because the behavior's origin
// request policy (elyoxe-cinema-geo) lists them. The city name wins over the region: Al Ain sits in the
// Abu Dhabi region. Nothing is logged; the answer is private, no-store (never cached, per visitor).
var CITY = {
    'abu dhabi': 'abu-dhabi', 'abudhabi': 'abu-dhabi', 'musaffah': 'abu-dhabi', 'mussafah': 'abu-dhabi',
    'khalifa city': 'abu-dhabi', 'mohamed bin zayed city': 'abu-dhabi', 'ruwais': 'abu-dhabi', 'madinat zayed': 'abu-dhabi',
    'al ain': 'al-ain', 'alain': 'al-ain', 'ain': 'al-ain', 'al ain city': 'al-ain',
    'dubai': 'dubai', 'jebel ali': 'dubai', 'hatta': 'dubai',
    'sharjah': 'sharjah', 'ash shariqah': 'sharjah', 'khor fakkan': 'sharjah', 'khawr fakkan': 'sharjah',
    'kalba': 'sharjah', 'dibba al hisn': 'sharjah',
    'ajman': 'ajman', 'ajman city': 'ajman',
    'ras al khaimah': 'ras-al-khaimah', 'ras al khaymah': 'ras-al-khaimah', 'rak': 'ras-al-khaimah',
    'fujairah': 'fujairah', 'al fujairah': 'fujairah', 'al fujayrah': 'fujairah', 'dibba al fujairah': 'fujairah',
    'umm al quwain': 'umm-al-quwain', 'umm al qaiwain': 'umm-al-quwain', 'umm al qawain': 'umm-al-quwain'
};
// ISO 3166-2:AE subdivision codes (CloudFront-Viewer-Country-Region)
var REGION = { AZ: 'abu-dhabi', DU: 'dubai', SH: 'sharjah', AJ: 'ajman', RK: 'ras-al-khaimah', FU: 'fujairah', UQ: 'umm-al-quwain' };
// CloudFront-Viewer-Country-Region-Name, when the code is missing
var REGION_NAME = { 'abu dhabi': 'abu-dhabi', 'dubai': 'dubai', 'sharjah': 'sharjah', 'ajman': 'ajman',
    'ras al khaimah': 'ras-al-khaimah', 'fujairah': 'fujairah', 'umm al quwain': 'umm-al-quwain' };

function norm(s) {
    if (!s) return '';
    try { s = decodeURIComponent(s); } catch (e) {}
    s = s.toLowerCase().replace(/[‘’'`]/g, '').replace(/[^a-z]+/g, ' ').trim();
    if (s.indexOf('emirate of ') === 0) s = s.slice(11);
    return s;
}

function cityOf(country, city, region, regionName) {
    if ((country || '').toUpperCase() !== 'AE') return null;
    var c = norm(city);
    if (CITY[c]) return CITY[c];
    var r = (region || '').toUpperCase();
    if (REGION[r]) return REGION[r];
    var n = norm(regionName);
    return REGION_NAME[n] || null;
}

function h(headers, k) { return headers[k] ? headers[k].value : ''; }

function handler(event) {
    var hs = event.request.headers;
    var city = cityOf(h(hs, 'cloudfront-viewer-country'), h(hs, 'cloudfront-viewer-city'),
        h(hs, 'cloudfront-viewer-country-region'), h(hs, 'cloudfront-viewer-country-region-name'));
    return {
        statusCode: 200,
        statusDescription: 'OK',
        headers: {
            'content-type': { value: 'application/json; charset=utf-8' },
            'cache-control': { value: 'private, no-store' },
            'x-content-type-options': { value: 'nosniff' }
        },
        body: { encoding: 'text', data: JSON.stringify({ city: city }) }
    };
}
