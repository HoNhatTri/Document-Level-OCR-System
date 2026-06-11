import { useEffect, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Card } from "./ui/card";
import { Button } from "./ui/button";

interface AIField {
  value: any;
  confidence?: number;
  source?: string;
  source_box_ids?: string[];
  raw?: string;
  currency?: string | null;
}

interface AIWarning {
  type: string;
  message: string;
  severity?: "low" | "medium" | "high";
  source_box_ids?: string[];
}

interface LayoutRegion {
  id: string;
  type: string;
  label: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  text?: string;
  confidence?: number;
  source?: string;
}

interface GenericKVPair {
  label: string;
  value: string;
  display_value?: string;
  canonical?: string | null;
  source?: string;
  confidence?: number;
}

interface AIAnalysis {
  document_type: string;
  document_type_confidence?: number;
  summary?: string;
  fields?: Record<string, AIField>;
  warnings?: AIWarning[];
  suggested_tables?: any[];
  layout_regions?: LayoutRegion[];
  generic_kv?: {
    key_values?: GenericKVPair[];
    sections?: GenericKVPair[];
  };
}

interface ExtractedData {
  text: string;
  tables: Array<{
    id: string;
    name: string;
    headers: string[];
    rows: string[][];
  }>;
  json: Record<string, any>;
  bounding_boxes?: Array<Record<string, any>>;
  ai?: AIAnalysis | null;
}

interface ResultsPanelProps {
  data: ExtractedData;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  matchedField?: string | null;
  sourceBoxIds?: string[];
}

function formatConfidence(value?: number) {
  if (typeof value !== "number") return "";
  return `${Math.round(value * 100)}%`;
}

function formatFieldValue(field: AIField) {
  const value = field.value;
  const displayValue = Array.isArray(value)
    ? value.join(", ")
    : typeof value === "object" && value !== null
      ? JSON.stringify(value)
      : String(value ?? "");

  if (field.raw && field.raw !== displayValue) {
    return `${displayValue} (${field.raw})`;
  }
  if (field.currency) {
    return `${displayValue} ${field.currency}`;
  }
  return displayValue;
}

const documentTypeLabels: Record<string, string> = {
  invoice: "Hóa đơn",
  contract: "Hợp đồng",
  receipt: "Biên lai/Phiếu thu",
  warehouse_note: "Phiếu kho",
  form: "Biểu mẫu hành chính",
  general_document: "Tài liệu tổng quát",
};

const layoutTypeLabels: Record<string, string> = {
  title: "Tiêu đề",
  header: "Đầu trang",
  table: "Bảng",
  important_info: "Thông tin quan trọng",
  total: "Tổng tiền",
  signature: "Chữ ký",
  left_column: "Cột trái",
  right_column: "Cột phải",
  paragraph: "Đoạn văn",
  footer: "Chân trang",
};

const fieldNameLabels: Record<string, string> = {
  primary_date: "Ngày chính",
  dates: "Ngày tháng",
  emails: "Email",
  phone_numbers: "Số điện thoại",
  tax_codes: "Mã số thuế",
  total_amount: "Tổng tiền",
  invoice_number: "Số hóa đơn",
  party_a: "Bên A",
  party_b: "Bên B",
  seller: "Người bán",
  buyer: "Người mua",
  buyer_address: "Địa chỉ người mua",
  seller_address: "Địa chỉ người bán",
  shipping_address: "Địa chỉ giao hàng",
  billing_address: "Địa chỉ thanh toán",
  payment_method: "Hình thức thanh toán",
  invoice_form: "Mẫu số",
  invoice_symbol: "Ký hiệu",
  amount_in_words: "Số tiền bằng chữ",
};

const warningSeverityLabels: Record<string, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  info: "Thông tin",
};

const warningTypeLabels: Record<string, string> = {
  empty_text: "Không có văn bản",
  low_confidence_word: "Từ có độ tin cậy thấp",
  missing_total_amount: "Thiếu tổng tiền",
  missing_tax_code: "Thiếu mã số thuế",
};

const quickQuestions = [
  "Tổng tiền trong hóa đơn là bao nhiêu?",
  "Ai là bên mua?",
  "Người bán là ai?",
  "Số hóa đơn là gì?",
  "Hình thức thanh toán là gì?",
  "Tài liệu này nói về nội dung gì?",
];

export function ResultsPanel({ data }: ResultsPanelProps) {
  const aiFields = data.ai?.fields ? Object.entries(data.ai.fields) : [];
  const layoutRegions = data.ai?.layout_regions || [];
  const genericKeyValues = data.ai?.generic_kv?.key_values || [];
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);

  useEffect(() => {
    setChatMessages([]);
    setQuestion("");
  }, [data.text, data.json]);

  const askQuestion = async (inputQuestion?: string) => {
    const trimmedQuestion = (inputQuestion ?? question).trim();
    if (!trimmedQuestion || isAsking) return;

    const userMessage: ChatMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      content: trimmedQuestion,
    };
    setChatMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setIsAsking(true);

    try {
      const response = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: trimmedQuestion,
          extracted_text: data.text,
          json_data: data.json,
          bounding_boxes: data.bounding_boxes || [],
          ai_analysis: data.ai,
        }),
      });

      if (!response.ok) {
        let message = "Không thể hỏi đáp trên tài liệu này.";
        try {
          const errorBody = await response.json();
          message = errorBody.detail || message;
        } catch {
          message = await response.text() || message;
        }
        throw new Error(message);
      }

      const result = await response.json();
      const assistantMessage: ChatMessage = {
        id: `${Date.now()}-assistant`,
        role: "assistant",
        content: result.answer || "Chưa tìm thấy câu trả lời rõ ràng trong tài liệu.",
        matchedField: result.matched_field,
        sourceBoxIds: result.source_box_ids || [],
      };
      setChatMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Không thể hỏi đáp trên tài liệu này.";
      setChatMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-assistant-error`,
          role: "assistant",
          content: message,
          matchedField: null,
          sourceBoxIds: [],
        },
      ]);
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-white border-l overflow-hidden">
      <Tabs defaultValue="text" className="flex flex-col h-full w-full overflow-hidden">
        <div className="border-b px-4 py-3 shrink-0 bg-white z-10">
          <TabsList className="w-full justify-start">
            <TabsTrigger value="text">Text</TabsTrigger>
            <TabsTrigger value="table">Table</TabsTrigger>
            <TabsTrigger value="json">JSON</TabsTrigger>
            <TabsTrigger value="ai">AI</TabsTrigger>
          </TabsList>
        </div>

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

          <TabsContent value="ai" className="m-0 space-y-4">
            {data.ai ? (
              <>
                <Card className="p-4 bg-white shadow-sm border-gray-200 space-y-3">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-gray-500">Loại tài liệu</div>
                    <div className="text-sm font-semibold text-gray-900">
                      {documentTypeLabels[data.ai.document_type] || data.ai.document_type}
                      {data.ai.document_type_confidence !== undefined && (
                        <span className="ml-2 text-xs font-normal text-gray-500">
                          {formatConfidence(data.ai.document_type_confidence)}
                        </span>
                      )}
                    </div>
                  </div>

                  {data.ai.summary && (
                    <div>
                      <div className="text-xs uppercase tracking-wide text-gray-500">Tóm tắt</div>
                      <p className="text-sm text-gray-800 leading-relaxed">{data.ai.summary}</p>
                    </div>
                  )}
                </Card>

                <Card className="p-4 bg-white shadow-sm border-gray-200">
                  <div className="font-semibold text-sm mb-3">Hỏi đáp trên tài liệu</div>

                  <div className="flex flex-wrap gap-2 mb-3">
                    {quickQuestions.map((quickQuestion) => (
                      <button
                        key={quickQuestion}
                        type="button"
                        className="text-xs rounded-md border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-gray-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 transition-colors"
                        onClick={() => askQuestion(quickQuestion)}
                        disabled={isAsking}
                      >
                        {quickQuestion}
                      </button>
                    ))}
                  </div>

                  <div className="space-y-3 max-h-72 overflow-y-auto pr-1 mb-3">
                    {chatMessages.length > 0 ? (
                      chatMessages.map((message) => (
                        <div
                          key={message.id}
                          className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                        >
                          <div
                            className={`max-w-[85%] rounded-md px-3 py-2 text-sm leading-relaxed ${
                              message.role === "user"
                                ? "bg-blue-600 text-white"
                                : "bg-gray-100 text-gray-900 border border-gray-200"
                            }`}
                          >
                            <div className="whitespace-pre-wrap break-words">{message.content}</div>
                            {message.role === "assistant" && (message.matchedField || (message.sourceBoxIds && message.sourceBoxIds.length > 0)) && (
                              <div className="mt-2 text-[11px] text-gray-500">
                                {message.matchedField && `Trường: ${fieldNameLabels[message.matchedField] || message.matchedField}`}
                                {message.sourceBoxIds && message.sourceBoxIds.length > 0 && ` / Vùng: ${message.sourceBoxIds.join(", ")}`}
                              </div>
                            )}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-sm text-gray-500 py-4 text-center">
                        Nhập câu hỏi hoặc chọn một câu hỏi gợi ý.
                      </div>
                    )}
                  </div>

                  <form
                    className="flex gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      askQuestion();
                    }}
                  >
                    <input
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      placeholder="Hỏi về tổng tiền, bên mua, ngày, mã số thuế..."
                      className="flex-1 min-w-0 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                      disabled={isAsking}
                    />
                    <Button type="submit" size="sm" className="gap-2 shrink-0" disabled={!question.trim() || isAsking}>
                      {isAsking ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                      Gửi
                    </Button>
                  </form>
                </Card>

                <Card className="p-4 bg-white shadow-sm border-gray-200">
                  <div className="font-semibold text-sm mb-3">Trường đã trích xuất</div>
                  {aiFields.length > 0 ? (
                    <div className="space-y-3">
                      {aiFields.map(([name, field]) => (
                        <div key={name} className="border-b last:border-b-0 pb-3 last:pb-0">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-xs font-medium text-gray-500 break-all">
                              {fieldNameLabels[name] || name}
                            </div>
                            {field.confidence !== undefined && (
                              <div className="text-xs text-gray-500 shrink-0">
                                {formatConfidence(field.confidence)}
                              </div>
                            )}
                          </div>
                          <div className="text-sm text-gray-900 break-words mt-1">
                            {formatFieldValue(field)}
                          </div>
                          {field.source && (
                            <div className="text-xs text-gray-400 mt-1">{field.source}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500">Chưa tìm thấy trường có cấu trúc.</div>
                  )}
                </Card>

                <Card className="p-4 bg-white shadow-sm border-gray-200">
                  <div className="font-semibold text-sm mb-3">Nhãn - giá trị tự phát hiện</div>
                  {genericKeyValues.length > 0 ? (
                    <div className="space-y-3">
                      {genericKeyValues.slice(0, 12).map((pair, index) => (
                        <div key={`${pair.label}-${index}`} className="border-b last:border-b-0 pb-3 last:pb-0">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-xs font-medium text-gray-500 break-words">{pair.label}</div>
                              <div className="text-sm text-gray-900 break-words whitespace-pre-wrap mt-1">
                                {pair.display_value || pair.value}
                              </div>
                            </div>
                            {pair.confidence !== undefined && (
                              <div className="text-xs text-gray-500 shrink-0">{formatConfidence(pair.confidence)}</div>
                            )}
                          </div>
                          {(pair.canonical || pair.source) && (
                            <div className="text-xs text-gray-400 mt-1">
                              {pair.canonical || "generic"} / {pair.source || "unknown"}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500">Chưa phát hiện cặp nhãn - giá trị nào.</div>
                  )}
                </Card>

                <Card className="p-4 bg-white shadow-sm border-gray-200">
                  <div className="font-semibold text-sm mb-3">Bố cục tài liệu</div>
                  {layoutRegions.length > 0 ? (
                    <div className="space-y-3">
                      {layoutRegions.map((region) => (
                        <div key={region.id} className="border-b last:border-b-0 pb-3 last:pb-0">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-sm font-medium text-gray-900">{region.label}</div>
                              <div className="text-xs text-gray-500">
                                {layoutTypeLabels[region.type] || region.type} / trang {region.page}
                                {region.confidence !== undefined && ` / ${formatConfidence(region.confidence)}`}
                              </div>
                            </div>
                            <div className="text-[11px] text-gray-400 text-right shrink-0">
                              x{region.x} y{region.y}
                              <br />
                              {region.width} x {region.height}
                            </div>
                          </div>
                          {region.text && (
                            <div className="text-xs text-gray-600 mt-2 line-clamp-3 whitespace-pre-wrap">
                              {region.text}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500">Chưa tìm thấy vùng bố cục.</div>
                  )}
                </Card>

                <Card className="p-4 bg-white shadow-sm border-gray-200">
                  <div className="font-semibold text-sm mb-3">Cảnh báo</div>
                  {data.ai.warnings && data.ai.warnings.length > 0 ? (
                    <div className="space-y-2">
                      {data.ai.warnings.map((warning, index) => (
                        <div key={`${warning.type}-${index}`} className="rounded-md border border-amber-200 bg-amber-50 p-3">
                          <div className="text-xs font-medium text-amber-800 uppercase">
                            {warningSeverityLabels[warning.severity || "info"] || warning.severity || "Thông tin"} / {warningTypeLabels[warning.type] || warning.type}
                          </div>
                          <div className="text-sm text-amber-950 mt-1">{warning.message}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500">Không có cảnh báo.</div>
                  )}
                </Card>
              </>
            ) : (
              <div className="text-center text-gray-500 py-8 text-sm">
                Chưa có kết quả AI agent cho tài liệu này.
              </div>
            )}
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
