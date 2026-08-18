<?php
// Public read-only receiver for Vineyard Operations.
// The publish token may be supplied as VINEYARD_PUBLISH_TOKEN or in the private
// cPanel file one directory above public_html: baiamonte-vineyard-config.php.
declare(strict_types=1);

$storageDir = __DIR__ . '/_vineyard_data';
$storageFile = $storageDir . '/public-vineyard.json';
$method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: public, max-age=300');
header('Access-Control-Allow-Origin: *');

function tb_public_variety(mixed $value): bool {
    $name = strtolower(trim(preg_replace('/\s+/', ' ', (string)$value) ?? ''));
    return in_array($name, ['grecanico', 'grenache', 'nerello mascalese'], true);
}

function tb_sanitize_public_feed(array $payload): array {
    if (isset($payload['items']) && is_array($payload['items'])) {
        $payload['items'] = array_values(array_filter(
            $payload['items'],
            static fn($item): bool => is_array($item) && tb_public_variety($item['variety'] ?? '')
        ));
    }
    if (isset($payload['vintages']) && is_array($payload['vintages'])) {
        foreach ($payload['vintages'] as $year => $items) {
            if (!is_array($items)) {
                unset($payload['vintages'][$year]);
                continue;
            }
            $payload['vintages'][$year] = array_values(array_filter(
                $items,
                static fn($item): bool => is_array($item) && tb_public_variety($item['variety_name'] ?? $item['variety'] ?? '')
            ));
        }
    }
    if (isset($payload['estate']) && is_array($payload['estate'])) {
        unset(
            $payload['estate']['total_area_ha'],
            $payload['estate']['vineyard_area_ha'],
            $payload['estate']['block_count'],
            $payload['estate']['parcel_count']
        );
    }
    return $payload;
}

if ($method === 'PUT') {
    $expected = '';
    $privateConfig = dirname(__DIR__) . '/baiamonte-vineyard-config.php';
    if (is_file($privateConfig)) {
        $settings = require $privateConfig;
        if (is_array($settings)) {
            $expected = (string)($settings['publish_token'] ?? '');
        }
    }
    if ($expected === '') {
        $expected = (string)getenv('VINEYARD_PUBLISH_TOKEN');
    }
    $authorization = (string)($_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '');
    if ($authorization === '' && function_exists('getallheaders')) {
        $headers = getallheaders();
        $authorization = (string)($headers['Authorization'] ?? $headers['authorization'] ?? '');
    }
    $provided = (string)($_SERVER['HTTP_X_VINEYARD_TOKEN'] ?? '');
    if ($provided === '' && str_starts_with($authorization, 'Bearer ')) {
        $provided = substr($authorization, 7);
    }
    if ($expected === '' || !hash_equals($expected, $provided)) {
        http_response_code(401);
        echo json_encode(['ok' => false, 'error' => 'Unauthorized']);
        exit;
    }
    $raw = file_get_contents('php://input');
    if ($raw === false || strlen($raw) > 2 * 1024 * 1024) {
        http_response_code(413);
        echo json_encode(['ok' => false, 'error' => 'Invalid payload']);
        exit;
    }
    $payload = json_decode($raw, true);
    if (!is_array($payload) || ($payload['schema_version'] ?? 0) < 1 || !isset($payload['estate'], $payload['updated_at'])) {
        http_response_code(422);
        echo json_encode(['ok' => false, 'error' => 'Invalid vineyard feed']);
        exit;
    }
    $payload = tb_sanitize_public_feed($payload);
    if (!is_dir($storageDir) && !mkdir($storageDir, 0750, true) && !is_dir($storageDir)) {
        http_response_code(500);
        echo json_encode(['ok' => false, 'error' => 'Storage unavailable']);
        exit;
    }
    $temporary = $storageFile . '.tmp';
    if (file_put_contents($temporary, json_encode($payload, JSON_UNESCAPED_SLASHES), LOCK_EX) === false || !rename($temporary, $storageFile)) {
        http_response_code(500);
        echo json_encode(['ok' => false, 'error' => 'Could not save feed']);
        exit;
    }
    echo json_encode(['ok' => true, 'updated_at' => $payload['updated_at']]);
    exit;
}

if ($method !== 'GET') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed']);
    exit;
}

if (!is_file($storageFile)) {
    http_response_code(503);
    echo json_encode(['ok' => false, 'error' => 'Vineyard feed has not published yet']);
    exit;
}

$raw = file_get_contents($storageFile);
$payload = $raw ? json_decode($raw, true) : null;
if (!is_array($payload)) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Stored feed is invalid']);
    exit;
}
$payload = tb_sanitize_public_feed($payload);
$payload['ok'] = true;
echo json_encode($payload, JSON_UNESCAPED_SLASHES);
