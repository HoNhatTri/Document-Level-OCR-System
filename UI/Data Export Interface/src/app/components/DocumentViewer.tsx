import { useState } from "react";
import { ZoomIn, ZoomOut, RotateCw, Copy } from "lucide-react";
import { Button } from "./ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { toast } from "sonner";
import { cn } from "./ui/utils";

interface BoundingBox {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  type: "text" | "table" | "image";
}

interface DocumentViewerProps {
  imageUrl: string;
  boundingBoxes: BoundingBox[];
  onBoxClick?: (box: BoundingBox) => void;
}

export function DocumentViewer({ imageUrl, boundingBoxes, onBoxClick }: DocumentViewerProps) {
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 0.5, 3));
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 0.25, 0.5));
  const handleRotate = () => setRotation((prev) => (prev + 90) % 360);

  const handleCopy = (text: string, box: BoundingBox) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success("Đã copy nội dung vào khay nhớ tạm!");
    onBoxClick?.(box);
  };

  return (
    <div className="flex flex-col h-full bg-gray-100">
      {/* THANH CÔNG CỤ */}
      <div className="flex items-center gap-2 p-3 bg-white border-b shrink-0 z-10">
        <Button variant="outline" size="sm" onClick={handleZoomOut}>
          <ZoomOut className="size-4" />
        </Button>
        <span className="text-sm font-medium min-w-16 text-center">
          {Math.round(zoom * 100)}%
        </span>
        <Button variant="outline" size="sm" onClick={handleZoomIn}>
          <ZoomIn className="size-4" />
        </Button>
        <div className="w-px h-6 bg-gray-300 mx-2" />
        <Button variant="outline" size="sm" onClick={handleRotate}>
          <RotateCw className="size-4" />
        </Button>
      </div>

      {/* KHU VỰC VIEW ẢNH - Sửa lại cấu trúc thẻ div */}
      <div className="flex-1 overflow-auto bg-gray-100 relative">
        <div 
          className="relative flex items-center justify-center min-w-full min-h-full p-8"
        >
          {/* KHUNG CHỨA ẢNH & BOUNDING BOX */}
          <div 
            className="relative inline-block align-middle text-left whitespace-normal transition-transform duration-200"
            style={{
              transform: `scale(${zoom}) rotate(${rotation}deg)`,
              transformOrigin: "left top"
            }}
          >
            <img 
              src={imageUrl} 
              alt="Document" 
              className="shadow-lg block"
              style={{
                maxWidth: "100%",
                maxHeight: "85vh"
              }}
            />
            
            {/* LỚP PHỦ BOUNDING BOXES */}
            <div className="absolute inset-0 w-full h-full pointer-events-none">
              <TooltipProvider delayDuration={150}>
                {boundingBoxes.map((box, idx) => (
                  <Tooltip key={box.id || idx}>
                    <TooltipTrigger asChild>
                      <div
                        className={cn(
                          "absolute border-2 pointer-events-auto cursor-pointer transition-all duration-200",
                          box.type === "table" ? "border-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/30" :
                          box.type === "image" ? "border-amber-500 bg-amber-500/10 hover:bg-amber-500/30" :
                          "border-blue-500 bg-blue-500/10 hover:bg-blue-500/30 hover:shadow-[0_0_10px_rgba(59,130,246,0.5)]"
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
                    <TooltipContent 
                      className="bg-gray-900 text-white border-gray-800 p-3 max-w-[300px] shadow-2xl z-[100]" 
                      side="bottom"
                    >
                      <p className="text-sm">{box.label || "Không có nội dung"}</p>
                    </TooltipContent>
                  </Tooltip>
                ))}
              </TooltipProvider>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}