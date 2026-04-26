-- KEYS[1] = counter key
-- ARGV[1] = increment
-- ARGV[2] = limit
-- ARGV[3] = ttl_seconds
local current = tonumber(redis.call("GET", KEYS[1]) or "0")
local increment = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local projected = current + increment
if projected > limit then
  return {0, current}
end
redis.call("SET", KEYS[1], projected, "EX", tonumber(ARGV[3]))
return {1, projected}

