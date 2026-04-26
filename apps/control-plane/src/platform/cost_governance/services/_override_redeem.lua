-- KEYS[1] = override token key
-- KEYS[2] = redeemed marker key
-- ARGV[1] = redeemed marker ttl seconds
if redis.call("EXISTS", KEYS[2]) == 1 then
  return "already_redeemed"
end
local value = redis.call("GET", KEYS[1])
if not value then
  return nil
end
redis.call("DEL", KEYS[1])
redis.call("SET", KEYS[2], "1", "EX", tonumber(ARGV[1]))
return value
