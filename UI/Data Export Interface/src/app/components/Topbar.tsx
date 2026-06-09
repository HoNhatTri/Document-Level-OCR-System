import { FileText, ChevronDown, FileDown } from "lucide-react";
import { buttonVariants } from "./ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

interface TopbarProps {
  currentFileName: string;
  onExport: (format: string) => void;
}

export function Topbar({ currentFileName, onExport }: TopbarProps) {
  return (
    <div className="h-16 border-b z-50 bg-white flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <FileText className="size-8 text-blue-600" />
          <span className="font-semibold text-xl">DocExtract</span>
        </div>
        <div className="h-6 w-px bg-gray-300" />
        <span className="text-gray-700">{currentFileName || "Chưa chọn file"}</span>
      </div>
      
      <DropdownMenu>
        {/* ĐÃ SỬA Ở ĐÂY: Bỏ asChild và dùng buttonVariants trực tiếp */}
        <DropdownMenuTrigger 
          className={buttonVariants({ variant: "default", className: "gap-2 cursor-pointer outline-none" })}
        >
          Xuất dữ liệu
          <ChevronDown className="size-4" />
        </DropdownMenuTrigger>
        
        <DropdownMenuContent align="end" className="w-48 bg-white shadow-lg">
          
          <DropdownMenuItem 
            onClick={() => onExport("pdf")} 
            className="cursor-pointer font-medium text-blue-600 focus:bg-blue-50"
          >
            <FileDown className="mr-2 size-4" />
            Xuất PDF (.pdf)
          </DropdownMenuItem>
          
          <DropdownMenuSeparator />
          
          <DropdownMenuItem 
            onClick={() => onExport("docx")} 
            className="cursor-pointer font-medium text-blue-600 focus:bg-blue-50"
          >
            <FileText className="mr-2 size-4" />
            Xuất Word (.docx)
          </DropdownMenuItem>

        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}