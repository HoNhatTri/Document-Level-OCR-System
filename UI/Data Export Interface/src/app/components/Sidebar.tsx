import { Upload, Clock, Settings, FileText } from "lucide-react";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { cn } from "./ui/utils";

interface ProcessedFile {
  id: string;
  name: string;
  date: string;
  status: "completed" | "processing" | "error";
}

interface SidebarProps {
  files: ProcessedFile[];
  currentFileId: string | null;
  onFileSelect: (id: string) => void;
  onUpload: () => void;
  onSettings: () => void;
}

export function Sidebar({ files, currentFileId, onFileSelect, onUpload, onSettings }: SidebarProps) {
  return (
    <div className="w-64 border-r bg-gray-50 flex flex-col">
      <div className="p-4">
        <Button 
          onClick={onUpload}
          className="w-full gap-2"
          size="lg"
        >
          <Upload className="size-4" />
          Upload
        </Button>
      </div>

      <div className="px-4 py-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 mb-2">
          <Clock className="size-4" />
          <span>Lịch sử</span>
        </div>
      </div>

      <ScrollArea className="flex-1 px-2">
        <div className="space-y-1 pb-4">
          {files.map((file) => (
            <button
              key={file.id}
              onClick={() => onFileSelect(file.id)}
              className={cn(
                "w-full text-left px-3 py-2 rounded-md transition-colors",
                "hover:bg-gray-200",
                currentFileId === file.id ? "bg-blue-100 text-blue-700" : "text-gray-700"
              )}
            >
              <div className="flex items-start gap-2">
                <FileText className="size-4 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{file.name}</div>
                  <div className="text-xs text-gray-500">{file.date}</div>
                  <div className={cn(
                    "text-xs mt-1",
                    file.status === "completed" && "text-green-600",
                    file.status === "processing" && "text-yellow-600",
                    file.status === "error" && "text-red-600"
                  )}>
                    {file.status === "completed" && "Hoàn thành"}
                    {file.status === "processing" && "Đang xử lý"}
                    {file.status === "error" && "Lỗi"}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>

      <div className="p-4 border-t">
        <Button
          onClick={onSettings}
          variant="ghost"
          className="w-full justify-start gap-2"
        >
          <Settings className="size-4" />
          Cài đặt
        </Button>
      </div>
    </div>
  );
}
