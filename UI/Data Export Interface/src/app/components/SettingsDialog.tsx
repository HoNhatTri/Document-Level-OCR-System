import { Image, Moon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Switch } from "./ui/switch";

export interface AppSettings {
  image_preprocessing_enabled: boolean;
  theme: "light" | "dark";
}

interface SettingsDialogProps {
  open: boolean;
  settings: AppSettings;
  isSaving: boolean;
  onOpenChange: (open: boolean) => void;
  onSettingsChange: (settings: AppSettings) => void;
  onSave: () => void;
}

export function SettingsDialog({
  open,
  settings,
  isSaving,
  onOpenChange,
  onSettingsChange,
  onSave,
}: SettingsDialogProps) {
  const updateSetting = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>Cài đặt</DialogTitle>
          <DialogDescription>
            Điều chỉnh cách hệ thống xử lý ảnh và giao diện.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <SettingRow
            icon={<Image className="size-4" />}
            title="Tiền xử lý ảnh"
            description="Tự tăng chất lượng ảnh, phát hiện ảnh xéo và deskew trước OCR."
            checked={settings.image_preprocessing_enabled}
            onCheckedChange={(checked) => updateSetting("image_preprocessing_enabled", checked)}
          />
          <SettingRow
            icon={<Moon className="size-4" />}
            title="Giao diện tối"
            description="Chuyển toàn bộ giao diện sang nền tối."
            checked={settings.theme === "dark"}
            onCheckedChange={(checked) => updateSetting("theme", checked ? "dark" : "light")}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Đóng
          </Button>
          <Button onClick={onSave} disabled={isSaving}>
            {isSaving ? "Đang lưu..." : "Lưu cài đặt"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SettingRow({
  icon,
  title,
  description,
  checked,
  onCheckedChange,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border bg-card p-4">
      <div className="flex min-w-0 gap-3">
        <div className="mt-0.5 text-muted-foreground">{icon}</div>
        <div>
          <div className="text-sm font-semibold text-card-foreground">{title}</div>
          <div className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</div>
        </div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
