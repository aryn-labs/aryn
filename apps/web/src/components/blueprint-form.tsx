import { useState } from "react";
import { Button } from "./ui/button";
import { Notice } from "./shared";
export function BlueprintForm({
  onSubmit,
  pending,
  error,
}: {
  onSubmit: (data: { name: string; slug: string; description: string }) => void;
  pending: boolean;
  error?: string;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [validation, setValidation] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (
          name.trim().length < 2 ||
          !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug) ||
          slug.length < 2
        ) {
          setValidation(
            "Isi nama minimal dua karakter dan slug dengan huruf kecil, angka, atau tanda hubung.",
          );
          return;
        }
        setValidation("");
        onSubmit({ name: name.trim(), slug, description: description.trim() });
      }}
      noValidate
    >
      <div className="form-fields">
        <label>
          Nama agent
          <input
            autoFocus
            value={name}
            maxLength={100}
            placeholder="Contoh: Analis Riset Produk"
            onChange={(e) => {
              setName(e.target.value);
              setSlug(
                e.target.value
                  .toLowerCase()
                  .replace(/[^a-z0-9]+/g, "-")
                  .replace(/^-|-$/g, ""),
              );
            }}
            required
          />
        </label>
        <label>
          Slug
          <span className="field-hint">
            ID yang mudah dibaca dan unik di proyek ini.
          </span>
          <input
            value={slug}
            maxLength={80}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="analis-riset-produk"
            required
            className="mono"
          />
        </label>
        <label>
          Deskripsi <span className="optional">opsional</span>
          <textarea
            value={description}
            maxLength={2000}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Tujuan, cakupan, dan hasil yang diharapkan dari agent."
            rows={3}
          />
        </label>
        {(error || validation) && (
          <Notice tone="error">{error || validation}</Notice>
        )}
      </div>
      <div className="dialog-footer">
        <span>Disimpan ke database lokal</span>
        <Button type="submit" disabled={pending}>
          {pending ? "Menyimpan…" : "Buat blueprint"}
        </Button>
      </div>
    </form>
  );
}
