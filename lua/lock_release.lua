local key = KEYS[1]
local token = ARGV[1]
local current = redis.call("GET", key)

if not current then
  return 0
end

if current == token then
  redis.call("DEL", key)
  return 1
end

return 0

