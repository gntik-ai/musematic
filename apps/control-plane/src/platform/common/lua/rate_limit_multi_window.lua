local function current_count(key)
  return tonumber(redis.call("GET", key) or "0")
end

local function ttl_ms(key, fallback_seconds)
  local value = tonumber(redis.call("PTTL", key) or "0")
  if value < 0 then
    return fallback_seconds * 1000
  end
  return value
end

local min_limit = tonumber(ARGV[1])
local hour_limit = tonumber(ARGV[2])
local day_limit = tonumber(ARGV[3])
local min_ttl = tonumber(ARGV[4])
local hour_ttl = tonumber(ARGV[5])
local day_ttl = tonumber(ARGV[6])

local min_current = current_count(KEYS[1])
local hour_current = current_count(KEYS[2])
local day_current = current_count(KEYS[3])

local min_allowed = min_current < min_limit
local hour_allowed = hour_current < hour_limit
local day_allowed = day_current < day_limit

if not (min_allowed and hour_allowed and day_allowed) then
  local retry_after_ms = math.max(
    min_allowed and 0 or ttl_ms(KEYS[1], min_ttl),
    hour_allowed and 0 or ttl_ms(KEYS[2], hour_ttl),
    day_allowed and 0 or ttl_ms(KEYS[3], day_ttl)
  )
  return {
    0,
    math.max(min_limit - min_current, 0),
    math.max(hour_limit - hour_current, 0),
    math.max(day_limit - day_current, 0),
    retry_after_ms
  }
end

redis.call("INCR", KEYS[1])
redis.call("INCR", KEYS[2])
redis.call("INCR", KEYS[3])

if min_current == 0 then
  redis.call("EXPIRE", KEYS[1], min_ttl)
end
if hour_current == 0 then
  redis.call("EXPIRE", KEYS[2], hour_ttl)
end
if day_current == 0 then
  redis.call("EXPIRE", KEYS[3], day_ttl)
end

return {
  1,
  min_limit - min_current - 1,
  hour_limit - hour_current - 1,
  day_limit - day_current - 1,
  0
}
