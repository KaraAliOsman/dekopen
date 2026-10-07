import { useRef, useState } from "react";

import { ApiError } from "../../api/apiMutator";
import { fieldPhotoUpload } from "../../api/generated/dekopen";
import { t } from "../../i18n/es-CL";

export type FieldPhoto = { key: string; sha256?: string; label?: string };

/** Foto de terreno: se comprime a JPEG ≤ 4 MB, se sube al registro y el
 * payload solo referencia la clave — la evidencia siempre tiene contexto
 * (la URL firmada no viaja en los formularios). */
async function compress(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new ApiError(0, null);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", 0.82),
  );
  if (!blob) throw new ApiError(0, null);
  const buffer = await blob.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < bytes.length; index += 8192) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 8192));
  }
  return window.btoa(binary);
}

export function PhotoField({
  orgId,
  label,
  photos,
  onChange,
  disabled,
}: {
  orgId: string;
  label: string;
  photos: FieldPhoto[];
  onChange: (photos: FieldPhoto[]) => void;
  disabled?: boolean;
}): JSX.Element {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const capture = async (file: File) => {
    setBusy(true);
    setFailed(false);
    try {
      const content = await compress(file);
      const response = await fieldPhotoUpload(
        { content_b64: content, label },
        { headers: { "X-Organization-ID": orgId } },
      );
      if (response.status !== 201) {
        throw new ApiError(response.status, response.data);
      }
      onChange([...photos, { key: response.data.key, sha256: response.data.sha256 }]);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="field-photo">
      <input
        ref={inputRef}
        accept="image/*"
        aria-label={label}
        capture="environment"
        className="field-photo__input"
        disabled={disabled || busy}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void capture(file);
        }}
        type="file"
      />
      <span className="field-photo__count">
        {photos.length > 0
          ? t("field.photoCount").replace("{count}", String(photos.length))
          : label}
      </span>
      {busy ? <span className="field-photo__busy">{t("field.photoUploading")}</span> : null}
      {failed ? <span className="field-photo__error">{t("field.photoFailed")}</span> : null}
    </div>
  );
}
