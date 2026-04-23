local key = KEYS[1]
local token = ARGV[1]
local ttl_seconds = tonumber(ARGV[2])
local current = redis.call("GET", key)

if not current then
  redis.call("SET", key, token, "EX", ttl_seconds)
  return 1
end

if current == token then
  redis.call("EXPIRE", key, ttl_seconds)
  return 1
end

return 0

