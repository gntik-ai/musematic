local key = KEYS[1]
local current_time_ms = tonumber(ARGV[1])
local window_size_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local window_start = current_time_ms - window_size_ms

redis.call("ZREMRANGEBYSCORE", key, "-inf", window_start)

local current_count = tonumber(redis.call("ZCARD", key))
if current_count < limit then
  local member = tostring(current_time_ms) .. ":" .. tostring(math.random(100000, 999999))
  redis.call("ZADD", key, current_time_ms, member)
  redis.call("PEXPIRE", key, window_size_ms + 1000)
  return {1, limit - (current_count + 1), 0}
end

local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
local retry_after_ms = window_size_ms
if oldest and #oldest >= 2 then
  retry_after_ms = math.max(window_size_ms - (current_time_ms - tonumber(oldest[2])), 0)
end

return {0, 0, retry_after_ms}

