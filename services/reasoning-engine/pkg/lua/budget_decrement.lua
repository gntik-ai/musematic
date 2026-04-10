local key = KEYS[1]
local field = ARGV[1]
local amount = tonumber(ARGV[2])
local current = tonumber(redis.call("HGET", key, field) or "0")
local max_value = tonumber(redis.call("HGET", key, "max_" .. string.sub(field, 6)) or "0")

if current + amount > max_value then
  return -1
end

return redis.call("HINCRBYFLOAT", key, field, amount)
