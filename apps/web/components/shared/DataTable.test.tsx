import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/shared/DataTable";

interface Row {
  name: string;
  owner: string;
}

const columns: ColumnDef<Row>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "owner", header: "Owner" },
];

const data: Row[] = [
  { name: "Runtime Controller", owner: "Platform" },
  { name: "Sandbox Manager", owner: "Security" },
];

describe("DataTable", () => {
  it("renders rows and filters them", () => {
    render(<DataTable columns={columns} data={data} />);

    fireEvent.change(screen.getByLabelText("Filter rows"), {
      target: { value: "Sandbox" },
    });

    expect(screen.getByText("Sandbox Manager")).toBeInTheDocument();
  });

  it("renders an empty state", () => {
    render(<DataTable columns={columns} data={[]} />);
    expect(screen.getByText("No rows found")).toBeInTheDocument();
  });
});
