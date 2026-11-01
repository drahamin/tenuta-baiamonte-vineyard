<?php
declare(strict_types=1);

final class MobileReadRateLimit extends RuntimeException
{
    private int $retryAfterSeconds;

    public function __construct(int $retryAfterSeconds=60)
    {
        parent::__construct('mobile read rate limit exceeded');
        $this->retryAfterSeconds=max(1,min(60,$retryAfterSeconds));
    }

    public function retryAfterSeconds():int
    {
        return $this->retryAfterSeconds;
    }
}
