local budget_key = KEYS[1]
local current_time_ms = tonumber(ARGV[1])
local dimension = ARGV[2]
local amount = tonumber(ARGV[3])

local budget = redis.call("HGETALL", budget_key)
if not budget or #budget == 0 then
  return {0, -1, -1, -1, -1}
end

local values = {}
for i = 1, #budget, 2 do
  values[budget[i]] = budget[i + 1]
end

local start_time = tonumber(values["start_time"] or "0")
local max_time_ms = tonumber(values["max_time_ms"] or "0")
local elapsed_ms = current_time_ms - start_time
local remaining_time_ms = math.max(max_time_ms - elapsed_ms, 0)

if elapsed_ms >= max_time_ms then
  return {
    0,
    tonumber(values["max_tokens"]) - tonumber(values["used_tokens"]),
    tonumber(values["max_rounds"]) - tonumber(values["used_rounds"]),
    tonumber(values["max_cost"]) - tonumber(values["used_cost"]),
    remaining_time_ms
  }
end

local max_field = "max_" .. dimension
local used_field = "used_" .. dimension
local current_used = tonumber(values[used_field] or "0")
local max_value = tonumber(values[max_field] or "0")

if current_used + amount > max_value then
  return {
    0,
    tonumber(values["max_tokens"]) - tonumber(values["used_tokens"]),
    tonumber(values["max_rounds"]) - tonumber(values["used_rounds"]),
    tonumber(values["max_cost"]) - tonumber(values["used_cost"]),
    remaining_time_ms
  }
end

if dimension == "cost" then
  redis.call("HINCRBYFLOAT", budget_key, used_field, amount)
else
  redis.call("HINCRBY", budget_key, used_field, amount)
end

local updated_used_tokens = tonumber(redis.call("HGET", budget_key, "used_tokens") or "0")
local updated_used_rounds = tonumber(redis.call("HGET", budget_key, "used_rounds") or "0")
local updated_used_cost = tonumber(redis.call("HGET", budget_key, "used_cost") or "0")

return {
  1,
  tonumber(values["max_tokens"]) - updated_used_tokens,
  tonumber(values["max_rounds"]) - updated_used_rounds,
  tonumber(values["max_cost"]) - updated_used_cost,
  remaining_time_ms
}

