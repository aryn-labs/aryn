import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Runs } from "../features/runs";
import { SettingsPage } from "../features/settings";
import { executionReady, gatewayStatus } from "../lib/studio-state";
import { studioFixture } from "./studio-fixtures";

vi.mock("../components/canvas/aryn-canvas", () => ({
  ArynCanvas: () => <div />,
}));

describe("runtime, gateway dan model adalah dependency terpisah", () => {
  it("Pengaturan memakai nama Model Gateway tanpa menampilkan vendor", () => {
    const props = studioFixture();
    const { container } = render(
      <MemoryRouter>
        <SettingsPage
          workspace={props.workspace}
          data={props.data}
          theme="dark"
          setTheme={() => {}}
          refresh={() => {}}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByText("Model Gateway", { exact: true }),
    ).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/9router/i);
  });
  it.each(["offline", "discovery", "binding"])(
    "Hermes ready tidak melewati gate %s",
    (failure) => {
      const props = studioFixture();
      props.act = vi.fn(async () => ({}));
      props.workspace.runtime.ready = true;
      props.workspace.gateway.connected = failure !== "offline";
      props.workspace.gateway.discovery_valid = failure !== "discovery";
      props.workspace.gateway.runtime_binding_verified = failure !== "binding";
      expect(executionReady(props.workspace)).toBe(false);
      expect(gatewayStatus(props.workspace).tone).not.toBe("success");
      render(
        <MemoryRouter>
          <Runs {...props} />
        </MemoryRouter>,
      );
      fireEvent.change(screen.getByLabelText("Instruksi riset"), {
        target: { value: "Permintaan riset untuk pengujian." },
      });
      fireEvent.click(screen.getByRole("checkbox"));
      expect(
        screen.getByRole("button", { name: "Jalankan agent" }),
      ).toBeDisabled();
      expect(
        screen.queryByText(props.workspace.runtime.message),
      ).not.toBeInTheDocument();
      expect(props.act).not.toHaveBeenCalled();
    },
  );
  it("gateway terhubung dan binding valid dapat siap tanpa mengklaim selected model tersedia", () => {
    const props = studioFixture();
    props.workspace.runtime.ready = true;
    expect(executionReady(props.workspace)).toBe(true);
    props.workspace.models[0].availability = "unknown";
    render(
      <MemoryRouter>
        <Runs {...props} />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("button", { name: "Jalankan agent" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Ketersediaan model belum dapat diverifikasi/),
    ).toBeInTheDocument();
  });
});
