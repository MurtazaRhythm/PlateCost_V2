export type DashboardData = {
  restaurant_name: string;
  today: { total: number; count: number; currency: string };
  recent: RecentReceipt[];
};

export type RecentReceipt = {
  id: string;
  vendor: string;
  total: number | null;
  currency: string;
  date: string | null;
  time: string | null;
  created_at: string;
};

export type ReceiptItem = {
  name: string | null;
  quantity: number | null;
  unit_price: number | null;
  total_price: number | null;
  category: string | null;
  confidence: number | null;
};

export type ReceiptImage = {
  sequence_number: number;
  image_url: string | null;
};

export type Receipt = {
  id: string;
  receipt_session_id: string | null;
  vendor: string | null;
  date: string | null;
  subtotal: number | null;
  tax: number | null;
  tip: number | null;
  total: number | null;
  payment_method: string | null;
  category: string | null;
  currency: string;
  needs_review: boolean;
  created_at: string | null;
  items: ReceiptItem[];
  images: ReceiptImage[];
};

export type SessionInfo = {
  id: string;
  status: string;
  image_count: number;
  receipt_id: string | null;
};

export type ProcessStage = "uploading" | "reading" | "extracting" | "categorizing";
