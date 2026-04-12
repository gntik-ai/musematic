local failures_key = KEYS[1]
local tripped_key = KEYS[2]

local threshold = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local tripped_ttl = tonumber(ARGV[3])

local now = redis.call("TIME")
local current_seconds = tonumber(now[1])
local current_micros = tonumber(now[2])
local member = tostring(current_seconds) .. "-" .. tostring(current_micros)

redis.call("ZADD", failures_key, current_seconds, member)
redis.call("ZREMRANGEBYSCORE", failures_key, 0, current_seconds - window_seconds)

local count = redis.call("ZCARD", failures_key)
local tripped = 0

if count >= threshold then
    redis.call("SETEX", tripped_key, tripped_ttl, "1")
    tripped = 1
end

redis.call("EXPIRE", failures_key, window_seconds)

return {count, tripped}
