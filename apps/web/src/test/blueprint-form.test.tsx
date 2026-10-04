import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BlueprintForm } from "../components/blueprint-form";
describe("Formulir blueprint", () => {
  it("menolak nilai kosong dan slug tidak valid sebelum mutasi", async () => {
    const submit = vi.fn();
    render(<BlueprintForm pending={false} onSubmit={submit} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Buat blueprint" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Isi nama minimal dua karakter",
    );
    expect(submit).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Nama agent"), "Research Agent");
    const slug = screen.getByRole("textbox", { name: /Slug/ });
    await userEvent.clear(slug);
    await userEvent.type(slug, "Invalid Slug");
    await userEvent.click(
      screen.getByRole("button", { name: "Buat blueprint" }),
    );
    expect(submit).not.toHaveBeenCalled();
  });
  it("menghasilkan slug dan mengirim data pengguna yang valid", async () => {
    const submit = vi.fn();
    render(<BlueprintForm pending={false} onSubmit={submit} />);
    await userEvent.type(screen.getByLabelText("Nama agent"), "Analis Produk");
    await userEvent.type(
      screen.getByRole("textbox", { name: /Deskripsi/ }),
      "Riset dengan bukti.",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Buat blueprint" }),
    );
    expect(submit).toHaveBeenCalledWith({
      name: "Analis Produk",
      slug: "analis-produk",
      description: "Riset dengan bukti.",
    });
  });
  it("menampilkan kegagalan API dan menonaktifkan kirim selama mutasi", () => {
    render(
      <BlueprintForm
        pending
        error="Akses ditolak oleh Core."
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Akses ditolak oleh Core.",
    );
    expect(screen.getByRole("button", { name: "Menyimpan…" })).toBeDisabled();
  });
});
