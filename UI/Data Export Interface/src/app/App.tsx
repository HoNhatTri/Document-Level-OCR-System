import { useEffect, useState } from "react";
import { Topbar } from "./components/Topbar";
import { Sidebar } from "./components/Sidebar";
import { DocumentViewer } from "./components/DocumentViewer";
import { ResultsPanel } from "./components/ResultsPanel";
import { UploadDialog } from "./components/UploadDialog";
import { SettingsDialog, type AppSettings } from "./components/SettingsDialog";
import { toast } from "sonner";
import { Toaster } from "./components/ui/sonner";

const DEFAULT_SETTINGS: AppSettings = {
  image_preprocessing_enabled: true,
  theme: "light",
};

function applyTheme(theme: AppSettings["theme"]) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export default function App() {
  // Quản lý danh sách file và dữ liệu từ API
  const [files, setFiles] = useState<any[]>([]);
  const [currentFileId, setCurrentFileId] = useState<string | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<AppSettings>(() => {
    const savedTheme = window.localStorage.getItem("ocr-ui-theme");
    return {
      ...DEFAULT_SETTINGS,
      theme: savedTheme === "dark" ? "dark" : "light",
    };
  });
  const [draftSettings, setDraftSettings] = useState<AppSettings>(settings);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  
  // Lưu trữ dữ liệu OCR bóc tách được cho từng file
  const [boundingBoxes, setBoundingBoxes] = useState<Record<string, any[]>>({});
  const [extractedData, setExtractedData] = useState<Record<string, any>>({});

  // Các biến lấy dữ liệu của file đang được chọn
  const currentFile = files.find((f) => f.id === currentFileId);
  const currentBoundingBoxes = currentFileId ? boundingBoxes[currentFileId] || [] : [];
  const currentExtractedData = currentFileId ? extractedData[currentFileId] : null;

  useEffect(() => {
    applyTheme(settings.theme);
  }, [settings.theme]);

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/settings");
        if (!response.ok) return;
        const data = await response.json();
        const nextSettings: AppSettings = {
          image_preprocessing_enabled: Boolean(data.image_preprocessing_enabled),
          theme: data.theme === "dark" ? "dark" : "light",
        };
        setSettings(nextSettings);
        setDraftSettings(nextSettings);
        window.localStorage.setItem("ocr-ui-theme", nextSettings.theme);
      } catch (error) {
        console.warn("Khong the tai cai dat", error);
      }
    };

    loadSettings();
  }, []);

  const handleSettingsOpenChange = (open: boolean) => {
    if (open) {
      setDraftSettings(settings);
    }
    setSettingsOpen(open);
  };

  const handleExport = async (format: string) => {
    if (!currentFile || !currentExtractedData) {
      toast.error("Vui lòng xử lý tài liệu trước khi xuất!");
      return;
    }

    if (format === "pdf" || format === "docx") {
      toast.info(`Đang tạo file ${format.toUpperCase()}...`);
      try {
        const endpoint = format === "pdf" ? "export-pdf" : "export-docx";
        
        const response = await fetch(`http://localhost:8000/api/${endpoint}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(currentExtractedData.json),
        });

        if (!response.ok) throw new Error(`Lỗi tạo ${format}`);

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", `${currentFile.name.split('.')[0]}_exported.${format}`);
        document.body.appendChild(link);
        link.click();
        link.parentNode?.removeChild(link);

        toast.success(`Xuất file ${format.toUpperCase()} thành công!`);
      } catch (error) {
        toast.error(`Có lỗi xảy ra khi xuất ${format.toUpperCase()}!`);
        console.error(error);
      }
    }
  };

  const handleUpload = async (file: File) => {
    toast.info(`Đang xử lý file: ${file.name}...`);
    
    // Tạo ID ngẫu nhiên và tạo URL cục bộ để hiển thị ảnh trên UI
    const fileId = Date.now().toString(); 
    const imageUrl = URL.createObjectURL(file); 
    
    // Đưa file vào sidebar với trạng thái "Đang xử lý"
    const newFile = {
      id: fileId,
      name: file.name,
      date: new Date().toLocaleString("vi-VN"),
      status: "processing",
      imageUrl: imageUrl,
    };
    setFiles((prev) => [newFile, ...prev]);
    setCurrentFileId(fileId);
    setUploadDialogOpen(false); // Đóng popup

    // Đóng gói file gửi xuống Backend
    const formData = new FormData();
    formData.append("file", file);

    try {
      // GỌI API ĐẾN BACKEND PYTHON
      const response = await fetch("http://localhost:8000/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        let message = "Loi khi xu ly tai lieu tu Backend";
        try {
          const errorBody = await response.json();
          message = errorBody.detail || message;
        } catch {
          message = await response.text() || message;
        }
        throw new Error(message);
      }

      const result = await response.json();
      
      // Cập nhật kết quả OCR vào giao diện
      setExtractedData((prev) => ({
        ...prev,
        [fileId]: {
          text: result.extracted_text || "Không có nội dung text",
          tables: result.tables || [],
          json: result.json_data || {},
          bounding_boxes: result.bounding_boxes || [],
          ai: result.ai_analysis
            ? { ...result.ai_analysis, layout_regions: result.layout_regions || result.ai_analysis.layout_regions || [] }
            : null
        }
      }));

      // Nếu Backend trả về tọa độ khung chữ, cập nhật vào đây
      if (result.bounding_boxes) {
        setBoundingBoxes((prev) => ({...prev, [fileId]: result.bounding_boxes}));
      }

      const finalImageUrl = result.processed_image_base64 || imageUrl;

      // Đánh dấu file hoàn thành
      setFiles((prev) => prev.map(f => f.id === fileId ? { ...f, status: "completed", imageUrl: finalImageUrl } : f));
      toast.success("Xử lý tài liệu thành công!");
      
    } catch (error) {
      const message = error instanceof Error ? error.message : "Co loi xay ra khi goi Model OCR!";
      toast.error(message);
      setFiles((prev) => prev.map(f => f.id === fileId ? { ...f, status: "error" } : f));
      console.error(error);
    }
  };

  const handleSaveSettings = async () => {
    setIsSavingSettings(true);
    try {
      const response = await fetch("http://localhost:8000/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draftSettings),
      });
      if (!response.ok) throw new Error("Khong the luu cai dat");
      const saved = await response.json();
      const nextSettings: AppSettings = {
        image_preprocessing_enabled: Boolean(saved.image_preprocessing_enabled),
        theme: saved.theme === "dark" ? "dark" : "light",
      };
      setSettings(nextSettings);
      setDraftSettings(nextSettings);
      window.localStorage.setItem("ocr-ui-theme", nextSettings.theme);
      setSettingsOpen(false);
      toast.success("Đã lưu cài đặt");
    } catch (error) {
      toast.error("Không thể lưu cài đặt");
      console.error(error);
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleBoxClick = (box: any) => {
    toast.info(`Đã chọn vùng: ${box.label || 'Không tên'}`);
  };

  return (
    <div className="h-screen flex flex-col bg-background text-foreground">
      <Toaster />
      
      <Topbar 
        currentFileName={currentFile?.name || ""}
        onExport={handleExport}
      />

      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          files={files}
          currentFileId={currentFileId}
          onFileSelect={setCurrentFileId}
          onUpload={() => setUploadDialogOpen(true)}
          onSettings={() => handleSettingsOpenChange(true)}
        />

        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 overflow-hidden">
            {currentFile && (
              <DocumentViewer
                imageUrl={currentFile.imageUrl}
                boundingBoxes={currentBoundingBoxes}
                onBoxClick={handleBoxClick}
              />
            )}
          </div>

          <div className="w-[400px] overflow-hidden">
            {currentExtractedData && (
              <ResultsPanel data={currentExtractedData} />
            )}
          </div>
        </div>
      </div>

      <UploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onUpload={handleUpload}
      />

      <SettingsDialog
        open={settingsOpen}
        settings={draftSettings}
        isSaving={isSavingSettings}
        onOpenChange={handleSettingsOpenChange}
        onSettingsChange={setDraftSettings}
        onSave={handleSaveSettings}
      />
    </div>
  );
}
