local key = KEYS[1]
local quality = tonumber(ARGV[1])
local epsilon = tonumber(ARGV[2])
local prev_quality = tonumber(redis.call("HGET", key, "prev_quality") or "-1")
local prev_prev_quality = tonumber(redis.call("HGET", key, "prev_prev_quality") or "-1")

redis.call("HSET", key, "prev_prev_quality", prev_quality)
redis.call("HSET", key, "prev_quality", quality)

if epsilon <= 0 then
  return 0
end

if prev_quality < 0 or prev_prev_quality < 0 then
  return 0
end

local delta_one = math.abs(quality - prev_quality)
local delta_two = math.abs(prev_quality - prev_prev_quality)

if delta_one < epsilon and delta_two < epsilon then
  return 1
end

return 0
