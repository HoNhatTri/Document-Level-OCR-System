import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Card } from "./ui/card";
// Đã xóa import ScrollArea để dùng thanh cuộn mặc định mượt hơn

interface ExtractedData {
  text: string;
  tables: Array<{
    id: string;
    name: string;
    headers: string[];
    rows: string[][];
  }>;
  json: Record<string, any>;
}

interface ResultsPanelProps {
  data: ExtractedData;
}

export function ResultsPanel({ data }: ResultsPanelProps) {
  return (
    <div className="flex flex-col h-full w-full bg-white border-l overflow-hidden">
      <Tabs defaultValue="text" className="flex flex-col h-full w-full overflow-hidden">
        
        <div className="border-b px-4 py-3 shrink-0 bg-white z-10">
          <TabsList className="w-full justify-start">
            <TabsTrigger value="text">Text</TabsTrigger>
            <TabsTrigger value="table">Table</TabsTrigger>
            <TabsTrigger value="json">JSON</TabsTrigger>
          </TabsList>
        </div>

        {/* Phần Nội Dung - Dùng overflow-y-auto để tạo con lăn chuột */}
        <div className="flex-1 overflow-y-auto p-4 bg-gray-50/50">
          
          <TabsContent value="text" className="m-0">
            <Card className="p-4 bg-white shadow-sm border-gray-200">
              <pre className="whitespace-pre-wrap text-sm font-mono text-gray-800 break-words">
                {data.text}
              </pre>
            </Card>
          </TabsContent>

          <TabsContent value="table" className="m-0 space-y-4">
            {data.tables && data.tables.length > 0 ? (
              data.tables.map((table) => (
                <Card key={table.id} className="p-4 bg-white shadow-sm">
                  <h3 className="font-semibold mb-3">{table.name}</h3>
                  <div className="border rounded-lg overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {table.headers.map((header, index) => (
                            <TableHead key={index} className="bg-gray-50 font-semibold whitespace-nowrap">
                              {header}
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {table.rows.map((row, rowIndex) => (
                          <TableRow key={rowIndex}>
                            {row.map((cell, cellIndex) => (
                              <TableCell key={cellIndex} className="whitespace-nowrap">
                                {cell}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </Card>
              ))
            ) : (
              <div className="text-center text-gray-500 py-8 text-sm">
                Không tìm thấy bảng biểu nào trong tài liệu này.
              </div>
            )}
          </TabsContent>

          <TabsContent value="json" className="m-0">
            <Card className="p-4 bg-gray-900 text-gray-100 shadow-sm">
              <pre className="text-sm font-mono overflow-x-auto break-words whitespace-pre-wrap">
                {JSON.stringify(data.json, null, 2)}
              </pre>
            </Card>
          </TabsContent>

        </div>
      </Tabs>
    </div>
  );
}