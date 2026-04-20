"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Select } from "@/components/ui/select";
import { useAgents } from "@/lib/hooks/use-agents";
import { useSurveillanceSignals } from "@/lib/hooks/use-surveillance-signals";

export interface SurveillancePanelProps {
  agentId: string;
}

export function SurveillancePanel({ agentId }: SurveillancePanelProps) {
  const [selectedAgentId, setSelectedAgentId] = useState(agentId);
  const agents = useAgents({}, { enabled: true });
  const { signals } = useSurveillanceSignals(selectedAgentId);

  useEffect(() => {
    setSelectedAgentId(agentId);
  }, [agentId]);

  const agentOptions = useMemo(
    () =>
      [{ fqn: agentId, name: agentId }, ...agents.agents].filter(
        (agent, index, collection) =>
          collection.findIndex((entry) => entry.fqn === agent.fqn) === index,
      ),
    [agentId, agents.agents],
  );

  const chartData = useMemo(
    () =>
      signals.map((signal) => ({
        timestamp: new Date(signal.timestamp).toLocaleDateString(),
        score: signal.score,
      })),
    [signals],
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[260px,1fr]">
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="surveillance-agent-picker">
            Agent
          </label>
          <Select
            id="surveillance-agent-picker"
            value={selectedAgentId}
            onChange={(event) => setSelectedAgentId(event.target.value)}
          >
            {agentOptions.map((agent) => (
              <option key={agent.fqn} value={agent.fqn}>
                {agent.name}
              </option>
            ))}
          </Select>
          <div className="rounded-xl border border-border/70 bg-card/80 p-3 text-sm text-muted-foreground">
            Latest 20 surveillance signals for the selected agent.
          </div>
        </div>
        <div className="h-[220px] rounded-2xl border border-border/70 bg-card/80 p-3">
          <ResponsiveContainer>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" />
              <YAxis />
              <Tooltip />
              <Line dataKey="score" dot={false} stroke="#0f172a" strokeWidth={2} type="monotone" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="space-y-3">
        {signals.map((signal) => (
          <div key={signal.id} className="rounded-2xl border border-border/70 bg-card/80 p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium">{signal.signalType}</p>
              <span className="text-sm text-muted-foreground">{signal.score.toFixed(2)}</span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{signal.summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
