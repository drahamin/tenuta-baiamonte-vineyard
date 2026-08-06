<?php
// about.php - Tenuta Baiamonte About Page
// Vineyard facts, harvest and weather are supplied by the read-only MariaDB publisher.

$host = $_SERVER['HTTP_HOST'] ?? 'www.tenutabaiamonte.com';
$is_https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['SERVER_PORT'] ?? '') == 443);
$protocol = $is_https ? 'https' : 'http';
$base_url = $protocol . '://' . $host;

$wantDebug = isset($_GET['debug']) && $_GET['debug'] === '1';

// -----------------------------
// Cache & HTTP helpers
// -----------------------------
function tb_cache_dir(): string {
    $dir = __DIR__ . '/_cache';
    if (!is_dir($dir)) @mkdir($dir, 0755, true);
    return $dir;
}

function tb_cache_get(string $key, int $ttl_seconds) {
    $path = tb_cache_dir() . '/' . preg_replace('/[^a-zA-Z0-9_.-]/', '_', $key) . '.json';
    if (!is_file($path)) return null;
    $age = time() - (int)@filemtime($path);
    if ($age > $ttl_seconds) return null;
    $raw = @file_get_contents($path);
    return $raw ? json_decode($raw, true) : null;
}

function tb_cache_set(string $key, array $value): void {
    $path = tb_cache_dir() . '/' . preg_replace('/[^a-zA-Z0-9_.-]/', '_', $key) . '.json';
    @file_put_contents($path, json_encode($value, JSON_UNESCAPED_SLASHES), LOCK_EX);
}

function tb_http_get_json_verbose(string $url, array $opts = []): array {
    $headers = $opts['headers'] ?? [];
    $timeout = (int)($opts['timeout_seconds'] ?? 12);
    $follow = (bool)($opts['follow'] ?? false);
    $user = $opts['basic_user'] ?? null;
    $pass = $opts['basic_pass'] ?? null;

    $result = ['ok' => false, 'http' => null, 'error' => null, 'data' => null, 'body_snippet' => null, 'final_url' => $url];

    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_FOLLOWLOCATION => $follow,
            CURLOPT_CONNECTTIMEOUT => $timeout,
            CURLOPT_TIMEOUT => $timeout,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_USERAGENT => 'TenutaBaiamonte/1.0',
        ]);
        if ($user !== null && $pass !== null) {
            curl_setopt($ch, CURLOPT_HTTPAUTH, CURLAUTH_BASIC);
            curl_setopt($ch, CURLOPT_USERPWD, "$user:$pass");
        }
        $body = curl_exec($ch);
        $err = curl_error($ch);
        $http = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $final = curl_getinfo($ch, CURLINFO_EFFECTIVE_URL);
        curl_close($ch);

        $result['http'] = $http;
        $result['final_url'] = $final ?: $url;
        $result['body_snippet'] = mb_substr((string)$body, 0, 300);

        if ($body === false) {
            $result['error'] = $err ?: 'cURL error';
            return $result;
        }
        if ($http < 200 || $http >= 300) {
            $result['error'] = "HTTP $http";
            return $result;
        }
        $decoded = json_decode($body, true);
        if (!is_array($decoded)) {
            $result['error'] = 'Invalid JSON';
            return $result;
        }
        $result['ok'] = true;
        $result['data'] = $decoded;
        return $result;
    }

    // stream fallback
    $ctx = stream_context_create(['http' => ['method' => 'GET', 'header' => implode("\r\n", $headers), 'timeout' => $timeout]]);
    $body = @file_get_contents($url, false, $ctx);
    if ($body === false || $body === '') {
        $result['error'] = 'HTTP request failed';
        return $result;
    }
    $result['body_snippet'] = mb_substr($body, 0, 300);
    $decoded = json_decode($body, true);
    if (!is_array($decoded)) {
        $result['error'] = 'Invalid JSON';
        return $result;
    }
    $result['ok'] = true;
    $result['data'] = $decoded;
    return $result;
}

// -----------------------------
// Ecowitt data extraction
// -----------------------------
function tb_extract_ecowitt(array $raw): array {
    $data = $raw['data'] ?? null;
    if (!is_array($data)) return ['ok' => false];

    $outdoor = $data['outdoor'] ?? [];
    $wind    = $data['wind'] ?? [];
    $rain    = $data['rainfall'] ?? [];
    $solar   = $data['solar_and_uvi'] ?? ($data['solar_uvi'] ?? []);
    $pressure = $data['pressure'] ?? [];

    $val = fn($n) => is_array($n) ? ($n['value'] ?? $n['val'] ?? null) : null;
    $unit = fn($n) => is_array($n) ? ($n['unit'] ?? null) : null;

    $iso = null;
    $ts = $raw['time'] ?? ($data['time'] ?? null);
    if (is_numeric($ts)) $iso = gmdate('c', (int)$ts);
    elseif (is_string($ts) && $ts) {
        $parsed = strtotime($ts);
        if ($parsed !== false) $iso = gmdate('c', $parsed);
    }

    return [
        'ok' => true,
        'updated_at_utc' => $iso,
        'metrics' => [
            'temperature'       => ['value' => $val($outdoor['temperature'] ?? null),     'unit' => $unit($outdoor['temperature'] ?? null)],
            'humidity'          => ['value' => $val($outdoor['humidity'] ?? null),         'unit' => $unit($outdoor['humidity'] ?? null)],
            'dew_point'         => ['value' => $val($outdoor['dew_point'] ?? $outdoor['dewpoint'] ?? null), 'unit' => $unit($outdoor['dew_point'] ?? null)],
            'feels_like'        => ['value' => $val($outdoor['feels_like'] ?? $outdoor['feelslike'] ?? null), 'unit' => $unit($outdoor['feels_like'] ?? null)],
            'heat_index'        => ['value' => $val($outdoor['heat_index'] ?? null),       'unit' => $unit($outdoor['heat_index'] ?? null)],
            'wind_speed'        => ['value' => $val($wind['wind_speed'] ?? $wind['wind_speed_avg'] ?? null), 'unit' => $unit($wind['wind_speed'] ?? null)],
            'wind_gust'         => ['value' => $val($wind['wind_gust'] ?? null),           'unit' => $unit($wind['wind_gust'] ?? null)],
            'wind_direction'    => ['value' => $val($wind['wind_direction'] ?? null),      'unit' => $unit($wind['wind_direction'] ?? null)],
            'rain_rate'         => ['value' => $val($rain['rain_rate'] ?? null),           'unit' => $unit($rain['rain_rate'] ?? null)],
            'rain_daily'        => ['value' => $val($rain['rain_daily'] ?? $rain['rain_day'] ?? null), 'unit' => $unit($rain['rain_daily'] ?? null)],
            'solar_radiation'   => ['value' => $val($solar['solar_radiation'] ?? $solar['solarradiation'] ?? null), 'unit' => $unit($solar['solar_radiation'] ?? null)],
            'uv_index'          => ['value' => $val($solar['uvi'] ?? $solar['uv'] ?? null), 'unit' => $unit($solar['uvi'] ?? null)],
            'pressure_relative' => ['value' => $val($pressure['relative'] ?? $pressure['rel'] ?? null), 'unit' => $unit($pressure['relative'] ?? null)],
        ]
    ];
}

// -----------------------------
// Harvest API bases
// -----------------------------
function tb_harvest_api_bases(string $base_url): array {
    return [
        'https://cantinabaiamonte.com/harvest/api',
        'https://api.cantinabaiamonte.com/harvest',
        // Add future staging/mirror endpoints here if needed
    ];
}

// -----------------------------
// Fetch predicted harvest dates for 2026 (public API)
// -----------------------------
$harvest_ctx  = 'tenuta-baiamonte';
$harvest_year = (int)date('Y');

// Cache 6–12 hours (default: 8h)
$harvest_ttl_seconds = 8 * 60 * 60;

$harvest_cache_key = "harvest_predicted_{$harvest_ctx}_{$harvest_year}";
$harvest = $wantDebug ? null : tb_cache_get($harvest_cache_key, $harvest_ttl_seconds);

$harvest_status = ['online' => false, 'source' => 'cache', 'message' => 'Using last known data'];

if (!$harvest) {
    $attempts = [];
    $url = $base_url . "/vineyard-feed.php?year=" . rawurlencode((string)$harvest_year);

    $res = tb_http_get_json_verbose($url, [
        'headers'         => ['Accept: application/json'],
        'timeout_seconds' => 15,
        'follow'          => true,
    ]);
    $attempts[] = ['url' => $url, 'result' => $res];

    if ($res['ok'] && is_array($res['data'])) {
        $payload = $res['data'];

        // Normalize to: { ok: true, items: [...] }
        $items = null;
        $updated_at = null;

        $isList = array_keys($payload) === range(0, count($payload) - 1);
        if ($isList) {
            $items = $payload;
        } elseif (isset($payload['items']) && is_array($payload['items'])) {
            $items = $payload['items'];
            $updated_at = $payload['updated_at'] ?? null;
        } elseif (isset($payload['data']) && is_array($payload['data'])) {
            $items = $payload['data'];
            $updated_at = $payload['updated_at'] ?? null;
        } elseif (isset($payload['rows']) && is_array($payload['rows'])) {
            $items = $payload['rows'];
            $updated_at = $payload['updated_at'] ?? ($payload['updatedAt'] ?? null);
        } elseif (isset($payload['predictions']) && is_array($payload['predictions'])) {
            $items = $payload['predictions'];
            $updated_at = $payload['updated_at'] ?? ($payload['updatedAt'] ?? null);
        } elseif (isset($payload['results']) && is_array($payload['results'])) {
            $items = $payload['results'];
            $updated_at = $payload['updated_at'] ?? ($payload['updatedAt'] ?? null);
        } elseif (isset($payload[0]) && is_array($payload[0])) {
            // Some APIs return numeric keys but not flagged as list
            $items = $payload;
        }
        // If API returns object with predicted map (not an array), keep payload as-is
        if (!is_array($items) && isset($payload['ok']) && $payload['ok'] && isset($payload['predicted']) && is_array($payload['predicted'])) {
            $harvest = $payload;
            tb_cache_set($harvest_cache_key, $harvest);
            $harvest_status = ['online' => true, 'source' => 'server', 'message' => 'Live data'];
        }



        if (is_array($items)) {
            $harvest = [
                'ok'         => true,
                'ctx'        => $harvest_ctx,
                'year'       => $harvest_year,
                'items'      => $items,
                'updated_at' => $updated_at,
                'estate'     => $payload['estate'] ?? null,
                'weather'    => $payload['weather'] ?? null,
                'vintages'   => $payload['vintages'] ?? null,
            ];
            tb_cache_set($harvest_cache_key, $harvest);
            $harvest_status = ['online' => true, 'source' => 'server', 'message' => 'Live data'];
        }
    }
}

// Long-term emergency fallback
if (!$harvest || !($harvest['ok'] ?? false)) {
    $oldCache = tb_cache_get($harvest_cache_key, 86400 * 30); // up to 30 days
    if ($oldCache && ($oldCache['ok'] ?? false)) {
        $harvest = $oldCache;
        $harvest_status = ['online' => false, 'source' => 'old-cache', 'message' => 'Using last known data'];
    } else {
        $harvest = ['ok' => false];
        $harvest_status = ['online' => false, 'source' => 'none', 'message' => 'No harvest data available'];
    }
}

if ($wantDebug && isset($attempts)) {
    $harvest['_debug'] = [
        'attempts' => $attempts,
        'status'   => $harvest_status
    ];
}

// -----------------------------
// Fetch Ecowitt weather
// -----------------------------
$ecowitt_cache_key = 'ecowitt_realtime_v3_943cc6450a9f_tempC';
$ecowitt = $wantDebug ? null : tb_cache_get($ecowitt_cache_key, 120);
$ecowitt_status = ['online' => false, 'source' => 'cache', 'message' => 'Using last known weather data'];

if (!$ecowitt && !is_array($harvest['weather'] ?? null)) {
    $appKey = (string)getenv('ECOWITT_APPLICATION_KEY');
    $apiKey = (string)getenv('ECOWITT_API_KEY');
    $mac = (string)getenv('ECOWITT_DEVICE_MAC');
    if ($appKey !== '' && $apiKey !== '' && $mac !== '') {
    $url = "https://api.ecowitt.net/api/v3/device/real_time?application_key={$appKey}&api_key={$apiKey}&mac=" . rawurlencode($mac) . "&call_back=all&temp_unitid=1&wind_speed_unitid=7&rainfall_unitid=12&pressure_unitid=3";

    $res = tb_http_get_json_verbose($url);

    if ($res['ok'] && is_array($res['data']) && ($res['data']['code'] ?? null) === 0) {
        $ecowitt = tb_extract_ecowitt($res['data']);
        tb_cache_set($ecowitt_cache_key, $ecowitt);
        $ecowitt_status = [
            'online'  => true,
            'source'  => 'Baiamonte Station',
            'message' => 'Live weather data'
        ];
    }
    }
}

if (!$ecowitt || !($ecowitt['ok'] ?? false)) {
    $oldCache = tb_cache_get($ecowitt_cache_key, 86400 * 30);
    if ($oldCache && ($oldCache['ok'] ?? false)) {
        $ecowitt = $oldCache;
        $ecowitt_status = [
            'online'  => false,
            'source'  => 'old-cache',
            'message' => 'Using last known weather data'
        ];
    } else {
        $ecowitt = ['ok' => false];
        $ecowitt_status['message'] = 'No weather data available';
    }
}

if ($wantDebug && isset($res)) {
    $ecowitt['_debug'] = $res;
}

// Prefer the sanitized Vineyard Operations feed. This removes the website's
// dependency on direct database access and keeps MariaDB private.
if (($harvest['ok'] ?? false) && is_array($harvest['weather'] ?? null)) {
    $w = $harvest['weather'];
    $ecowitt = [
        'ok' => true,
        'updated_at_utc' => $w['observed_at'] ?? ($harvest['updated_at'] ?? null),
        'metrics' => [
            'temperature' => ['value' => $w['temp_c'] ?? null, 'unit' => '°C'],
            'humidity' => ['value' => $w['humidity_pct'] ?? null, 'unit' => '%'],
            'wind_speed' => ['value' => $w['wind_kph'] ?? null, 'unit' => 'km/h'],
            'wind_gust' => ['value' => $w['wind_gust_kph'] ?? null, 'unit' => 'km/h'],
            'rain_daily' => ['value' => $w['rain_mm'] ?? null, 'unit' => 'mm'],
            'solar_radiation' => ['value' => $w['solar_wm2'] ?? null, 'unit' => 'W/m²'],
            'uv_index' => ['value' => $w['uv_index'] ?? null, 'unit' => ''],
        ],
    ];
    $ecowitt_status = ['online' => true, 'source' => 'Baiamonte database', 'message' => 'Vineyard Operations feed'];
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, minimum-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="description" content="Learn about Tenuta Baiamonte, a Sicilian winery founded in 2023 by David and Wendy, dedicated to sustainable, terroir-driven wines from Mount Etna.">
    <meta name="keywords" content="Tenuta Baiamonte, Mount Etna winery, Sicilian winery, sustainable winemaking, volcanic terroir, David and Wendy">
    <meta name="robots" content="index, follow">
    <meta name="author" content="Tenuta Baiamonte">
    <link rel="canonical" href="<?= htmlspecialchars($base_url) ?>/about.html">

    <!-- Hreflang -->
    <link rel="alternate" hreflang="en" href="https://www.tenutabaiamonte.com/about.html">
    <link rel="alternate" hreflang="it" href="https://www.tenutabaiamonte.it/about.html">
    <link rel="alternate" hreflang="x-default" href="https://www.tenutabaiamonte.com/about.html">

    <!-- Open Graph / Social -->
    <meta property="og:title" content="Tenuta Baiamonte | A Terroir-Driven Winery on Mount Etna, Sicily">
    <meta property="og:description" content="Explore Tenuta Baiamonte, a winery on Mount Etna crafting unique Sicilian wines with volcanic terroir.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="<?= htmlspecialchars($base_url) ?>/about.html">
    <meta property="og:image" content="https://www.tenutabaiamonte.com/images/pmlogo.png">
    <meta property="og:image:alt" content="Tenuta Baiamonte Logo">

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Tenuta Baiamonte | A Terroir-Driven Winery on Mount Etna, Sicily">
    <meta name="twitter:description" content="Explore Tenuta Baiamonte, a winery on Mount Etna crafting unique Sicilian wines with volcanic terroir.">
    <meta name="twitter:image" content="https://www.tenutabaiamonte.com/images/pmlogo.png">

    <!-- Favicons -->
    <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">

    <title>About | Tenuta Baiamonte</title>
    <link href="https://fonts.cdnfonts.com/css/futura-lt" rel="stylesheet">
    <link rel="stylesheet" href="/css/styles-updated.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/weather-icons/2.0.12/css/weather-icons.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/weather-icons/2.0.12/css/weather-icons-wind.min.css">

    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-T13TZJEF0C"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-T13TZJEF0C');
    </script>

    <style>
        .hero.parallax {
            height: 100vh;
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            color: #fff;
            position: relative;
        }
        .hero.parallax .parallax-bg {
            position: absolute;
            inset: 0;
            background-image: url('/images/enter.jpeg');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            z-index: 0;
        }
        .hero.parallax::before {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(to bottom, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0.6) 60%, rgba(0,0,0,0.8) 100%);
            z-index: 1;
        }
        .hero.parallax > * { position: relative; z-index: 2; }
        @media (max-width: 1024px) {
            .hero.parallax, .hero.parallax .parallax-bg { background-attachment: scroll; }
        }

        .weather-box {
            margin: 30px auto;
            padding: 25px;
            background: rgba(255,255,255,0.9);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.12);
            border: 3px solid #d4af37;
            max-width: 600px;
            color: #333;
        }
        .weather-title {
            font-weight: 700;
            font-size: 1.3rem;
            margin-bottom: 15px;
            color: #8b4513;
            text-align: center;
        }
        .weather-main {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        .weather-icon-container { position: relative; display: inline-block; }
        .weather-icon { width: 120px; height: 120px; object-fit: contain; }
        .weather-main-temp { font-size: 2.8rem; font-weight: 800; }
        .wind-direction-container {
            position: absolute;
            bottom: -10px;
            right: -10px;
            width: 60px;
            height: 60px;
        }
        .wind-arrow {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 56px;
        }
        .weather-icon-fallback { font-size: 6rem; display: none; }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px;
            margin-top: 14px;
        }
        .metric {
            background: rgba(212,175,55,0.08);
            padding: 10px 12px;
            border-radius: 12px;
        }
        .metric .k {
            display: block;
            font-weight: 700;
            color: #8b4513;
            font-size: 0.92rem;
            margin-bottom: 4px;
        }
        .metric .v {
            font-size: 1.15rem;
            font-weight: 800;
            color: #222;
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
            color: #555;
            margin-top: 12px;
            justify-content: center;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            flex-shrink: 0;
        }
        .status-online  { background: #28a745; }
        .status-offline { background: #dc3545; }

        .harvest-item {
            padding: 14px 16px;
            border-radius: 10px;
            background: rgba(212,175,55,0.06);
            margin: 10px 0;
            border-left: 4px solid transparent;
            transition: all 0.2s;
        }
        .harvest-soon {
            border-left-color: #c0392b;
            background: rgba(192,57,43,0.08);
        }
        .harvest-past {
            opacity: 0.75;
            font-style: italic;
            color: #555;
        }
        .harvest-updated {
            font-size: 0.9rem;
            font-style: italic;
            color: #666;
            margin-top: 16px;
            text-align: center;
        }

        .debug-box {
            margin-top: 20px;
            font-size: 0.85rem;
            background: #f8f8f8;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #ddd;
        }
    </style>

    <script>
        window.__TB_ECOWITT__ = <?= json_encode($ecowitt, JSON_UNESCAPED_SLASHES) ?>;
        window.__TB_ECOWITT_STATUS__ = <?= json_encode($ecowitt_status, JSON_UNESCAPED_SLASHES) ?>;
        window.__TB_HARVEST__ = <?= json_encode($harvest, JSON_UNESCAPED_SLASHES) ?>;
        window.__TB_HARVEST_STATUS__ = <?= json_encode($harvest_status, JSON_UNESCAPED_SLASHES) ?>;
    </script>
</head>
<body>

    <!-- Schema.org markup -->
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Winery",
        "name": "Tenuta Baiamonte",
        "description": "A terroir-driven winery on the northern slope of Mount Etna, Sicily, crafting unique wines from volcanic soils.",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "SS284",
            "addressLocality": "Randazzo",
            "addressRegion": "CT",
            "postalCode": "95036",
            "addressCountry": "IT"
        },
        "email": "info@tenutabaiamonte.it",
        "url": "https://www.tenutabaiamonte.com",
        "sameAs": [
            "https://www.instagram.com/tenuta_baiamonte",
            "https://www.facebook.com/tenutabaiamonte/"
        ]
    }
    </script>

    <!-- Header -->
    <header id="main-header">
        <nav>
            <div class="logo-container">
                <a href="/index.html"><img src="/images/bmlogo.png" alt="Tenuta Baiamonte Logo" class="logo-img"></a>
            </div>
            <button class="hamburger" aria-label="Open Menu">
                <span class="bar"></span>
                <span class="bar"></span>
                <span class="bar"></span>
            </button>
            <ul class="nav-links">
                <li><a href="/index.html" id="nav-home">Home</a></li>
                <li><a href="/about.html" id="nav-about">About</a></li>
                <li><a href="/wines.html" id="nav-wines">Wines</a></li>
                <li><a href="#" id="nav-shopping">Shopping</a></li>
                <li><a href="/visit.html" id="nav-visit">Visit</a></li>
                <li><a href="/contact.html" id="nav-contact">Contact</a></li>
            </ul>
        </nav>
    </header>

    <!-- Hero -->
    <section class="hero parallax">
        <div class="parallax-bg"></div>
        <div>
            <h1 id="hero-title">Tenuta Baiamonte</h1>
            <p id="hero-subtitle">A love letter to Mother Etna</p>
        </div>
    </section>

    <!-- Our Story -->
    <section class="about-section" id="our-story">
        <h2 id="story-title">Our Story</h2>
        <div class="story-content">
            <div class="story-text">
                <p id="story-p1">In 2023, David and Wendy followed a quiet summons to Etna’s northern slope. At 959 meters, where chestnut forests dissolve into black sands and wild herbs whisper ancient secrets, they found home. Here, lava flows older than memory cradle vines that have endured centuries of fire and rebirth. Tenuta Baiamonte was born—not as conquest, but as surrender to the mountain’s will.</p>
                <p id="story-p2">Every gesture is reverence: organic farming, hands cradling fruit in small crates, spontaneous fermentation, aging in stillness. We intervene only to listen. The 'Mamma' series is our offering to the volcano’s dual soul—fierce guardian and boundless giver.</p>
            </div>
            <div class="story-image">
                <img src="/images/dw.jpeg" alt="David and Wendy, founders of Tenuta Baiamonte">
            </div>
        </div>
    </section>

    <!-- The Vineyard -->
    <section class="about-section" id="vineyard">
        <h2 id="vineyard-title">The Vineyard</h2>
        <div class="vineyard-content">
            <div class="vineyard-image">
                <img src="/images/vyair.jpeg" alt="Aerial view of Tenuta Baiamonte vineyard">
            </div>
            <div class="vineyard-text">
                <p id="vineyard-p">Our estate spans 11 hectares of volcanic land. The 3.5 best hectares were planted with vines right after World War II, mostly Piedirosso (known locally as Piè Franco) on original rootstock—a rare survivor that thrives in Etna’s mineral-rich volcanic soil, producing wines of profound depth and authenticity. Five hectares cling to volcanic terraces, kissed by fierce sun and cooled by altitude’s sigh. Bush-trained vines of Nerello Mascalese, Grecanico, and Grenache sink roots into mineral-rich sands, drinking iron, potassium, and the mountain’s silent song. Between rows, wild fennel, broom, and native grasses flourish—a living tapestry echoing Etna’s untamed heart.</p>

                <div id="weather-display" class="weather-box">
                    <p class="weather-loading">Loading current weather at Tenuta Baiamonte...</p>
                </div>

                <div id="harvest-display" class="weather-box">
                    <p class="weather-loading">Loading current vintage information...</p>
                </div>
            </div>
        </div>
    </section>

    <!-- Our Hands -->
    <section class="about-section" style="padding-top: 60px;">
        <h2 id="team-title">Our Hands</h2>
        <div class="story-content">
            <div class="story-text">
                <p id="team-p">A small circle guided by David and Wendy, joined by Etna-born hands and an enologist steeped in volcanic lore. We share one truth: the finest wines are not made, but unveiled. With quiet precision and deep respect, we tend, harvest, and guide—letting the mountain speak through every bottle.</p>
            </div>
            <div class="story-image">
                <img src="/images/hands.jpeg" alt="Wendy harvesting grapes at Tenuta Baiamonte">
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer>
        <p>info@tenutabaiamonte.it</p>
        <p id="footer-address">SS284 Randazzo, CT 95036, Sicily, Italy</p>
        <div class="social-links">
            <a href="https://www.instagram.com/tenuta_baiamonte" target="_blank" rel="noopener" aria-label="Instagram">
                <svg class="social-icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.791-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.209-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.441s.645 1.441 1.441 1.441 1.441-.645 1.441-1.441-.645-1.441-1.441-1.441z"/>
                </svg>
                Instagram
            </a>
            <a href="https://www.facebook.com/tenutabaiamonte/" target="_blank" rel="noopener" aria-label="Facebook">
                <svg class="social-icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M22.675 0h-21.35C.597 0 0 .597 0 1.325v21.351C0 23.403.597 24 1.325 24h11.495v-9.294H9.691v-3.622h3.129V8.413c0-3.1 1.893-4.788 4.659-4.788 1.325 0 2.463.099 2.795.143v3.24l-1.918.001c-1.504 0-1.795.715-1.795 1.763v2.313h3.587l-.467 3.622h-3.12V24h6.116c.728 0 1.325-.597 1.325-1.325V1.325C24 .597 23.403 0 22.675 0z"/>
                </svg>
                Facebook
            </a>
            <a href="https://g.page/r/CZ3e9gK0f8Z6EBM/review" target="_blank" rel="noopener" aria-label="Leave us a Google Review">
                <svg class="social-icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                </svg>
                Review
            </a>
        </div>
        <p id="footer-copyright"></p>
    </footer>

    <script>
        const translations = {
            en: {
                title: "About | Tenuta Baiamonte",
                navHome: "Home",
                navAbout: "About",
                navWines: "Wines",
                navShopping: "Shopping",
                navVisit: "Visit",
                navContact: "Contact",
                heroTitle: "Tenuta Baiamonte",
                heroSubtitle: "A love letter to Mother Etna",
                storyTitle: "Our Story",
                storyP1: "In 2023, David and Wendy followed a quiet summons to Etna’s northern slope. At 959 meters, where chestnut forests dissolve into black sands and wild herbs whisper ancient secrets, they found home. Here, lava flows older than memory cradle vines that have endured centuries of fire and rebirth. Tenuta Baiamonte was born—not as conquest, but as surrender to the mountain’s will.",
                storyP2: "Every gesture is reverence: organic farming, hands cradling fruit in small crates, spontaneous fermentation, aging in stillness. We intervene only to listen. The 'Mamma' series is our offering to the volcano’s dual soul—fierce guardian and boundless giver.",
                vineyardTitle: "The Vineyard",
                vineyardP: "Our estate spans 11 hectares of volcanic land. The 3.5 best hectares were planted with vines right after World War II, mostly Piedirosso (known locally as Piè Franco) on original rootstock—a rare survivor that thrives in Etna’s mineral-rich volcanic soil, producing wines of profound depth and authenticity. Five hectares cling to volcanic terraces, kissed by fierce sun and cooled by altitude’s sigh. Bush-trained vines of Nerello Mascalese, Grecanico, and Grenache sink roots into mineral-rich sands, drinking iron, potassium, and the mountain’s silent song. Between rows, wild fennel, broom, and native grasses flourish—a living tapestry echoing Etna’s untamed heart.",
                teamTitle: "Our Hands",
                teamP: "A small circle guided by David and Wendy, joined by Etna-born hands and an enologist steeped in volcanic lore. We share one truth: the finest wines are not made, but unveiled. With quiet precision and deep respect, we tend, harvest, and guide—letting the mountain speak through every bottle.",
                footerAddress: "SS284 Randazzo, CT 95036, Sicily, Italy",
                footerCopyrightBase: "Crafted with reverence on Etna’s northern slope.",
                weatherTitle: "Current Weather at Tenuta Baiamonte",
                weatherUnavailable: "Weather data currently unavailable",
                soilMoisture: "Soil Moisture (CH1)",
                harvestTitle: "Current Vintage — <?= (int)$harvest_year ?>",
                harvestUnavailable: "Harvest prediction data currently unavailable",
                harvestGrecanico: "Grecanico",
                harvestNerello: "Nerello Mascalese",
                harvestGrenache: "Grenache",
                harvestPredicted: "Estimated date",
                harvestUpdated: "Updated"
            },
            it: {
                title: "Chi Siamo | Tenuta Baiamonte",
                navHome: "Home",
                navAbout: "Chi Siamo",
                navWines: "Vini",
                navShopping: "Carrello",
                navVisit: "Visite",
                navContact: "Contatti",
                heroTitle: "Tenuta Baiamonte",
                heroSubtitle: "Una lettera d'amore a Madre Etna",
                storyTitle: "La Nostra Storia",
                storyP1: "Nel 2023, David e Wendy hanno seguito una chiamata silenziosa verso il versante nord dell’Etna. A 959 metri, dove i boschi di castagni si dissolvono in sabbie nere ed erbe selvatiche sussurrano segreti antichi, hanno trovato casa. Qui colate laviche più antiche della memoria cullano viti che hanno resistito a secoli di fuoco e rinascita. Tenuta Baiamonte è nata—non come conquista, ma come resa alla volontà della montagna.",
                storyP2: "Ogni gesto è reverenza: agricoltura biologica, mani che cullano il frutto in piccole cassette, fermentazione spontanea, invecchiamento nel silenzio. Interveniamo solo per ascoltare. La serie 'Mamma' è la nostra offerta all’anima duplice del vulcano—fiera guardiana e donatrice senza confini.",
                vineyardTitle: "Il Vigneto",
                vineyardP: "La nostra tenuta si estende su 11 ettari di terra vulcanica. I migliori 3,5 ettari sono stati piantati a vite subito dopo la Seconda Guerra Mondiale, principalmente Piedirosso (localmente chiamato Piè Franco) su portinnesto originale—un raro sopravvissuto che prospera nel suolo vulcanico ricco di minerali dell’Etna, producendo vini di profondità e autenticità profonde. Cinque ettari si aggrappano a terrazze vulcaniche, baciati dal sole feroce e rinfrescati dal sospiro dell’altitudine. Viti ad alberello di Nerello Mascalese, Grecanico e Grenache affondano radici in sabbie ricche di minerali, bevendo ferro, potassio e il canto silenzioso della montagna. Tra i filari prosperano finocchio selvatico, ginestra e graminacee autoctone—un arazzo vivo che riecheggia il cuore indomito dell’Etna.",
                teamTitle: "Le Nostre Mani",
                teamP: "Un piccolo cerchio guidato da David e Wendy, affiancato da mani nate sull’Etna e da un enologo immerso nella tradizione vulcanica. Condividiamo una verità: i vini più fini non si fanno, si svelano. Con precisione quieta e profondo rispetto, curiamo, raccogliamo e guidiamo—lasciando che la montagna parli attraverso ogni bottiglia.",
                footerAddress: "SS284 Randazzo, CT 95036, Sicilia, Italia",
                footerCopyrightBase: "Creato con reverenza sul versante nord dell’Etna.",
                weatherTitle: "Meteo Attuale a Tenuta Baiamonte",
                weatherUnavailable: "Dati meteo attualmente non disponibili",
                soilMoisture: "Umidità del Suolo (CH1)",
                harvestTitle: "Vendemmia Corrente — <?= (int)$harvest_year ?>",
                harvestUnavailable: "Dati previsione vendemmia attualmente non disponibili",
                harvestGrecanico: "Grecanico",
                harvestNerello: "Nerello Mascalese",
                harvestGrenache: "Grenache",
                harvestPredicted: "Data stimata",
                harvestUpdated: "Aggiornato"
            }
        };

        const lang = navigator.language.startsWith('it') ? 'it' : 'en';
        const texts = translations[lang];

        // Apply translations
        document.title = texts.title;
        document.getElementById('nav-home').textContent = texts.navHome;
        document.getElementById('nav-about').textContent = texts.navAbout;
        document.getElementById('nav-wines').textContent = texts.navWines;
        document.getElementById('nav-shopping').textContent = texts.navShopping;
        document.getElementById('nav-visit').textContent = texts.navVisit;
        document.getElementById('nav-contact').textContent = texts.navContact;
        document.getElementById('hero-title').textContent = texts.heroTitle;
        document.getElementById('hero-subtitle').textContent = texts.heroSubtitle;
        document.getElementById('story-title').textContent = texts.storyTitle;
        document.getElementById('story-p1').textContent = texts.storyP1;
        document.getElementById('story-p2').textContent = texts.storyP2;
        document.getElementById('vineyard-title').textContent = texts.vineyardTitle;
        document.getElementById('vineyard-p').textContent = texts.vineyardP;
        document.getElementById('team-title').textContent = texts.teamTitle;
        document.getElementById('team-p').textContent = texts.teamP;
        document.getElementById('footer-address').textContent = texts.footerAddress;
        document.getElementById('footer-copyright').innerHTML = `© ${new Date().getFullYear()} Tenuta Baiamonte. ${texts.footerCopyrightBase}`;

        document.getElementById('nav-shopping').href = lang === 'it' ? '/eushopping.html' : '/usshopping.html';

        // Hamburger menu
        const hamburger = document.querySelector('.hamburger');
        const navLinks = document.querySelector('.nav-links');
        if (hamburger && navLinks) {
            hamburger.addEventListener('click', () => {
                hamburger.classList.toggle('active');
                navLinks.classList.toggle('active');
                document.body.style.overflow = navLinks.classList.contains('active') ? 'hidden' : '';
            });
            document.querySelectorAll('.nav-links a').forEach(link => {
                link.addEventListener('click', () => {
                    hamburger.classList.remove('active');
                    navLinks.classList.remove('active');
                    document.body.style.overflow = '';
                });
            });
        }

        window.addEventListener('scroll', () => {
            document.getElementById('main-header').classList.toggle('scrolled', window.scrollY > 100);
        });

        function fmtMetric(m) {
            if (!m || m.value == null) return null;
            return m.value + (m.unit ? ` ${m.unit}` : '');
        }

        function fmtUpdated(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            if (isNaN(d.getTime())) return '';
            const locale = lang === 'it' ? 'it-IT' : 'en-US';
            return d.toLocaleString(locale, {
                year: 'numeric', month: 'long', day: 'numeric',
                hour: '2-digit', minute: '2-digit'
            }) + ' UTC';
        }

        function getConditionIcon(ecowitt) {
            if (!ecowitt?.ok || !ecowitt.metrics) return null;
            const m = ecowitt.metrics;

            const rainRate = parseFloat(m.rain_rate?.value) || 0;
            const solar = parseFloat(m.solar_radiation?.value) || 0;
            const windSpeedVal = parseFloat(m.wind_speed?.value) || 0;
            const windGustVal = parseFloat(m.wind_gust?.value) || windSpeedVal;
            const windDeg = parseFloat(m.wind_direction?.value) || null;

            const useSpeed = Math.max(windSpeedVal, windGustVal);

            let iconCode = '04d';
            let fallbackClass = 'wi wi-cloudy';

            if (rainRate > 2) { iconCode = '09d'; fallbackClass = 'wi wi-showers'; }
            else if (rainRate > 0.5) { iconCode = '10d'; fallbackClass = 'wi wi-rain'; }
            else if (useSpeed > 15) {
                if (solar > 600) iconCode = '02d', fallbackClass = 'wi wi-day-windy';
                else if (solar > 200) iconCode = '02d', fallbackClass = 'wi wi-cloudy-gusts';
                else iconCode = '04d', fallbackClass = 'wi wi-windy';
            }
            else if (solar > 700) { iconCode = '01d'; fallbackClass = 'wi wi-day-sunny'; }
            else if (solar > 400) { iconCode = '02d'; fallbackClass = 'wi wi-day-cloudy'; }
            else if (solar > 100) { iconCode = '03d'; fallbackClass = 'wi wi-cloudy'; }

            const iconUrl = `https://openweathermap.org/img/wn/${iconCode}@2x.png`;

            let arrowColorClass = 'wind-calm';
            if (windSpeedVal >= 40) arrowColorClass = 'wind-strong';
            else if (windSpeedVal >= 20) arrowColorClass = 'wind-fresh';
            else if (windSpeedVal >= 10) arrowColorClass = 'wind-moderate';
            else if (windSpeedVal >= 2) arrowColorClass = 'wind-light';

            return { url: iconUrl, fallback: fallbackClass, windDeg, windSpeed: windSpeedVal, arrowColorClass };
        }

        function renderWeather(ecowitt) {
            const el = document.getElementById('weather-display');
            if (!el) return;

            const status = window.__TB_ECOWITT_STATUS__ || { online: false, message: 'No status info' };
            const dotClass = status.online ? 'status-online' : 'status-offline';
            const statusHTML = `
                <div class="status-indicator">
                    <span class="status-dot ${dotClass}"></span>
                    <span>${status.message}</span>
                    ${status.source && status.source !== 'server' ? `<small>(${status.source})</small>` : ''}
                </div>
            `;

            if (!ecowitt?.ok || !ecowitt.metrics) {
                el.innerHTML = `
                    <p class="weather-title">${texts.weatherTitle}</p>
                    <p>${texts.weatherUnavailable}</p>
                    ${statusHTML}
                `;
                return;
            }

            const m = ecowitt.metrics;
            const temp = fmtMetric(m.temperature) || '?';
            const iconInfo = getConditionIcon(ecowitt);

            let soilMoisture = null;
            if (window.__TB_ECOWITT__?.metrics?.soilmoisture1?.value != null) {
                soilMoisture = window.__TB_ECOWITT__.metrics.soilmoisture1;
            }

            const rows = [
                { k: lang === 'it' ? 'Umidità' : 'Humidity', v: fmtMetric(m.humidity) },
                { k: lang === 'it' ? 'Percepita' : 'Feels like', v: fmtMetric(m.feels_like) },
                { k: lang === 'it' ? 'Punto di rugiada' : 'Dew point', v: fmtMetric(m.dew_point) },
                { k: lang === 'it' ? 'Vento' : 'Wind', v: fmtMetric(m.wind_speed) },
                { k: lang === 'it' ? 'Raffiche' : 'Gust', v: fmtMetric(m.wind_gust) },
                { k: lang === 'it' ? 'Direzione' : 'Direction', v: fmtMetric(m.wind_direction) },
                { k: lang === 'it' ? 'Pioggia (oggi)' : 'Rain (today)', v: fmtMetric(m.rain_daily) },
                { k: lang === 'it' ? 'Intensità pioggia' : 'Rain rate', v: fmtMetric(m.rain_rate) },
                { k: lang === 'it' ? 'Pressione (rel.)' : 'Pressure (rel.)', v: fmtMetric(m.pressure_relative) },
                { k: lang === 'it' ? 'Radiazione solare' : 'Solar radiation', v: fmtMetric(m.solar_radiation) },
                { k: 'UV', v: fmtMetric(m.uv_index) },
            ].filter(r => r.v != null);

            if (soilMoisture) {
                rows.unshift({
                    k: texts.soilMoisture,
                    v: soilMoisture.value + (soilMoisture.unit ? ` ${soilMoisture.unit}` : '')
                });
            }

            const updated = fmtUpdated(ecowitt.updated_at_utc);
            const updatedLine = updated ? `<p class="harvest-updated">${texts.harvestUpdated}: ${updated}</p>` : '';

            let iconHTML = `
                <div class="weather-icon-container">
                    <img src="${iconInfo.url}" alt="Weather" class="weather-icon"
                         onerror="this.style.display='none';this.nextElementSibling.style.display='block';">
                    <i class="${iconInfo.fallback} weather-icon-fallback"></i>
            `;

            if (iconInfo.windDeg != null && iconInfo.windSpeed > 1) {
                const blowToDeg = (iconInfo.windDeg + 180) % 360;
                const degClass = Math.round(blowToDeg);
                iconHTML += `
                    <div class="wind-direction-container">
                        <i class="wi wi-wind towards-${degClass}-deg wind-arrow ${iconInfo.arrowColorClass}"></i>
                    </div>
                `;
            }
            iconHTML += '</div>';

            el.innerHTML = `
                <p class="weather-title">${texts.weatherTitle}</p>
                <div class="weather-main">
                    ${iconHTML}
                    <div class="weather-main-temp">${temp}</div>
                </div>
                <div class="metric-grid">
                    ${rows.map(r => `
                        <div class="metric">
                            <span class="k">${r.k}</span>
                            <span class="v">${r.v}</span>
                        </div>
                    `).join('')}
                </div>
                ${updatedLine}
                ${statusHTML}
            `;
        }

        function renderHarvest(harvest) {
            const el = document.getElementById('harvest-display');
            if (!el) return;

            const status = window.__TB_HARVEST_STATUS__ || { online: false, message: 'No status info' };
            const dotClass = status.online ? 'status-online' : 'status-offline';
            const statusHTML = `
                <div class="status-indicator">
                    <span class="status-dot ${dotClass}"></span>
                    <span>${status.message}</span>
                    ${status.source && status.source !== 'server' ? `<small>(${status.source})</small>` : ''}
                </div>
            `;

            let items = harvest?.items || harvest?.rows || harvest?.predictions || harvest?.data || harvest?.results || (Array.isArray(harvest) ? harvest : null);

// Handle API shape: { ok:true, predicted: { updated_at, <variety>: "YYYY-MM-DD", <Variety>: {date, confidence, ...}, ... } }
if (!items && harvest?.predicted && typeof harvest.predicted === 'object') {
    const pred = harvest.predicted;
    const rows = [];
    for (const [k, v] of Object.entries(pred)) {
        if (k === 'updated_at' || k.startsWith('_')) continue;

        if (v && typeof v === 'object') {
            const pd = v.predicted_date || v.date || '';
            // If it doesn't look like a date, skip
            if (pd) {
                rows.push({
                    variety: k,
                    predicted_date: pd,
                    harvest_window_start: v.harvest_window_start || v.window_start || '',
                    harvest_window_end: v.harvest_window_end || v.window_end || '',
                    status: v.status || '',
                    confidence: (typeof v.confidence === 'number') ? v.confidence : null
                });
            }
        } else if (typeof v === 'string') {
            // Some varieties are keys mapping directly to a date string
            rows.push({
                variety: k,
                predicted_date: v,
                harvest_window_start: '',
                harvest_window_end: '',
                status: '',
                confidence: null
            });
        }
    }

    // Deduplicate (prefer entries with confidence/status/window)
    const byKey = new Map();
    for (const r of rows) {
        const key = String(r.variety || '').toLowerCase();
        const existing = byKey.get(key);
        const score = (r.confidence !== null ? 2 : 0) + (r.status ? 1 : 0) + ((r.harvest_window_start || r.harvest_window_end) ? 1 : 0);
        const existingScore = existing
            ? ((existing.confidence !== null ? 2 : 0) + (existing.status ? 1 : 0) + ((existing.harvest_window_start || existing.harvest_window_end) ? 1 : 0))
            : -1;
        if (!existing || score > existingScore) byKey.set(key, r);
    }
    items = Array.from(byKey.values());
}

            if (!Array.isArray(items)) {
                let debugHtml = '';
                if (new URLSearchParams(window.location.search).get('debug') === '1' && harvest?._debug) {
                    const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
                    debugHtml = `<details class="debug-box"><summary>Harvest API Debug</summary><pre>${esc(JSON.stringify(harvest._debug, null, 2))}</pre></details>`;
                }
                el.innerHTML = `
                    <p class="weather-title">${texts.harvestTitle}</p>
                    <p>${texts.harvestUnavailable}</p>
                    ${statusHTML}
                    ${debugHtml}
                `;
                return;
            }

            const today = new Date();

            const fmt = (s) => {
                if (!s) return '';
                // Keep ISO YYYY-MM-DD as-is; otherwise try Date parsing.
                if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
                const d = new Date(s);
                if (Number.isNaN(d.getTime())) return String(s);
                return d.toISOString().slice(0,10);
            };

            const rows = items
                .map(r => ({
                    variety: r?.variety || r?.name || '',
                    predicted_date: fmt(r?.predicted_date),
                    harvest_window_start: fmt(r?.harvest_window_start),
                    harvest_window_end: fmt(r?.harvest_window_end),
                    status: r?.status || '',
                    confidence: (typeof r?.confidence === 'number') ? r.confidence : null
                }))
                .filter(r => r.variety || r.predicted_date || r.harvest_window_start || r.harvest_window_end || r.status);

            // Sort by predicted date if present
            rows.sort((a,b) => {
                const ad = a.predicted_date ? new Date(a.predicted_date).getTime() : Number.POSITIVE_INFINITY;
                const bd = b.predicted_date ? new Date(b.predicted_date).getTime() : Number.POSITIVE_INFINITY;
                return ad - bd;
            });

            if (rows.length === 0) {
                el.innerHTML = `
                    <p class="weather-title">${texts.harvestTitle}</p>
                    <p style="text-align:center; padding:30px 0; color:#666;">
                        ${lang === 'it' ? 'Nessuna previsione disponibile al momento' : 'No predictions available yet'}
                    </p>
                    ${statusHTML}
                `;
                return;
            }

            const renderRow = (r) => {
                let daysHtml = '';
                if (r.predicted_date) {
                    const d = new Date(r.predicted_date);
                    if (!Number.isNaN(d.getTime())) {
                        const days = Math.round((d - today) / (1000 * 60 * 60 * 24));
                        const styleClass = days < 0 ? 'harvest-past' : (days <= 30 ? 'harvest-soon' : '');
                        const daysText = days >= 0 ? days : `–${Math.abs(days)}`;
                        daysHtml = ` <span class="${styleClass}">(${daysText} days)</span>`;
                    }
                }

                const windowStr = (r.harvest_window_start || r.harvest_window_end)
                  ? `${r.harvest_window_start || ''}${(r.harvest_window_start || r.harvest_window_end) ? ' – ' : ''}${r.harvest_window_end || ''}`.trim()
                  : '';

                const statusBadge = r.status
                  ? `<span class="harvest-status">${String(r.status).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</span>`
                  : '';

                return `
                    <div class="harvest-item">
                        <div class="harvest-line">
                            <strong>${String(r.variety).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</strong>
                            ${statusBadge}
                        </div>
                        <div class="harvest-sub">
                            ${r.predicted_date ? `${texts.harvestPredicted}: ${r.predicted_date}${daysHtml}` : ''}
                            ${windowStr ? `<div class="harvest-window">${lang === 'it' ? 'Finestra raccolta' : 'Harvest window'}: ${windowStr}</div>` : ''}
                        </div>
                    </div>
                `;
            };

            const itemsHtml = rows.map(renderRow).join('');

            const updated = fmtUpdated(harvest.updated_at || harvest.updatedAt || harvest?.predicted?.updated_at || null);
            const updatedHtml = updated ? `<p class="harvest-updated">${texts.harvestUpdated}: ${updated}</p>` : '';

            el.innerHTML = `
                <p class="weather-title">${texts.harvestTitle}</p>
                <div class="harvest-list">${itemsHtml}</div>
                ${updatedHtml}
                ${statusHTML}
            `;
        }

        document.addEventListener('DOMContentLoaded', () => {
            renderWeather(window.__TB_ECOWITT__);
            renderHarvest(window.__TB_HARVEST__);

            setTimeout(() => {
                if (document.querySelector('.weather-loading')) {
                    renderWeather(window.__TB_ECOWITT__);
                    renderHarvest(window.__TB_HARVEST__);
                }
            }, 8000);
        });
    </script>
</body>
</html>
