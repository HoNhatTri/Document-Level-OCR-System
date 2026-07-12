import { useState, useRef } from "react";
import { ZoomIn, ZoomOut, RotateCw, Copy } from "lucide-react";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { toast } from "sonner";
import { cn } from "./ui/utils";

export interface BoundingBox {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  type?: "text" | "table" | "image";
}

export interface DocumentViewerProps {
  imageUrl: string;
  boundingBoxes: BoundingBox[];
  onBoxClick?: (box: BoundingBox) => void;
}

export function DocumentViewer({ imageUrl, boundingBoxes, onBoxClick }: DocumentViewerProps) {
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 0.25, 3));
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 0.25, 0.5));
  const handleRotate = () => setRotation((prev) => (prev + 90) % 360);

  // Hàm xử lý copy text (an toàn với mọi trình duyệt)
  const handleCopy = (text: string, box: BoundingBox) => {
    if (!text) return;
    
    // Fallback cho việc copy vào clipboard
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text);
    } else {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      try {
        document.execCommand('copy');
      } catch (err) {
        console.error('Lỗi khi copy:', err);
      }
      document.body.removeChild(textArea);
    }
    
    toast.success("Đã copy nội dung");
    onBoxClick?.(box);
  };

  return (
    <div className="flex flex-col h-full bg-muted/20">
      {/* Toolbar */}
      <div className="flex items-center gap-2 p-2 border-b border-border bg-card">
        <Button variant="ghost" size="icon" onClick={handleZoomOut}>
          <ZoomOut className="h-4 w-4" />
        </Button>
        <span className="text-sm w-12 text-center">{Math.round(zoom * 100)}%</span>
        <Button variant="ghost" size="icon" onClick={handleZoomIn}>
          <ZoomIn className="h-4 w-4" />
        </Button>
        
        <div className="w-px h-4 bg-border mx-1" />
        
        <Button variant="ghost" size="icon" onClick={handleRotate}>
          <RotateCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Viewer Area */}
      <div 
        ref={containerRef}
        className="flex-1 overflow-auto p-4 flex items-center justify-center relative"
      >
        {/* Container ôm khít ảnh để Bounding Box tính theo % chuẩn xác nhất */}
        <div 
          className="relative shadow-md border border-border bg-white transition-transform duration-200 inline-block"
          style={{ 
            transform: `scale(${zoom}) rotate(${rotation}deg)`,
            transformOrigin: "center center"
          }}
        >
          {/* Hình ảnh */}
          <img 
            src={imageUrl} 
            alt="Document preview" 
            className="block max-w-[80vw] max-h-[80vh] object-contain pointer-events-none select-none"
          />
          
          {/* Lớp vẽ Bounding Boxes */}
          <TooltipProvider delayDuration={200}>
            {boundingBoxes?.map((box, i) => (
              <Tooltip key={`box-${box.id || i}`}>
                <TooltipTrigger asChild>
                  <div 
                    className={cn(
                      "absolute cursor-pointer transition-colors border",
                      box.type === "table" 
                        ? "border-red-500/40 bg-red-500/10 hover:bg-red-500/30 hover:shadow-[0_0_10px_rgba(239,68,68,0.5)]"
                        : box.type === "image"
                          ? "border-green-500/40 bg-green-500/10 hover:bg-green-500/30 hover:shadow-[0_0_10px_rgba(16,185,129,0.5)]"
                          : "border-blue-500/40 bg-blue-500/10 hover:bg-blue-500/30 hover:shadow-[0_0_10px_rgba(59,130,246,0.5)]"
                    )}
                    style={{
                      left: `${box.x}%`,
                      top: `${box.y}%`,
                      width: `${box.width}%`,
                      height: `${box.height}%`,
                    }}
                    onClick={() => handleCopy(box.label, box)}
                  />
                </TooltipTrigger>
                
                {/* Bảng Nội Dung Nổi Lên Khi Đưa Chuột Vào (Tooltip Content) */}
                <TooltipContent 
                  className="bg-gray-900 text-white border-gray-800 p-3 max-w-[300px] shadow-2xl z-[100]" 
                  side="bottom"
                  align="center"
                  sideOffset={4}
                >
                  <p className="text-sm font-medium leading-relaxed mb-3 break-words whitespace-pre-wrap">
                    {box.label || "Không có nội dung"}
                  </p>
                  <div className="flex items-center gap-1.5 text-xs text-blue-200 bg-blue-900/50 w-fit px-2.5 py-1.5 rounded-md border border-blue-800/50">
                    <Copy className="size-3" />
                    <span>Click để copy</span>
                  </div>
                </TooltipContent>
              </Tooltip>
            ))}
          </TooltipProvider>
        </div>
      </div>
    </div>
  );
}