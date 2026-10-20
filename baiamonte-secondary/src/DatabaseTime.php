<?php
declare(strict_types=1);

final class DatabaseTime
{
    public static function now(): string
    {
        return self::from('now');
    }

    public static function from(string $value, int $offsetSeconds=0): string
    {
        $time = new DateTimeImmutable($value, new DateTimeZone('UTC'));
        if ($offsetSeconds !== 0) {
            $time = $time->modify(($offsetSeconds > 0 ? '+' : '').$offsetSeconds.' seconds');
        }
        return $time->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.u');
    }
}
