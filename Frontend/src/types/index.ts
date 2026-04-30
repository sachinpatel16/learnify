export interface APIEnvelope<T> {
  success: boolean;
  message: string;
  data: T;
}

export interface Book {
  id: string;
  title: string;
  standard?: string | null;
  subject?: string | null;
  board?: string | null;
  language?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Subject {
  id: string;
  name: string;
  standard?: string | null;
  board?: string | null;
  language?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChapterDocument {
  id: string;
  book_id?: string | null;
  chapter_number?: number | null;
  chapter_title?: string | null;
  display_name?: string | null;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | string;
  is_processed: boolean;
  vector_namespace?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BookDetail extends Book {
  chapters: ChapterDocument[];
}


export interface ExamSectionInput {
  type: 'mcq' | 'short_answer';
  count: number;
  marks_each: number;
}

export interface ExamSpec {
  book_id: string;
  title: string;
  chapters: number[];
  sections: ExamSectionInput[];
  difficulty: 'easy' | 'medium' | 'hard';
  language: string;
  standard?: string | null;
  subject?: string | null;
  per_chapter_distribution: 'proportional' | 'evenly_split';
}

export interface Exam {
  id: string;
  book_id: string;
  title?: string | null;
  spec: Record<string, unknown>;
  paper?: ExamPaperViewPayload | null;
  total_marks: number;
  status: 'pending' | 'generating' | 'completed' | 'failed' | string;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaperQuestion {
  q_no: number;
  type: 'mcq' | 'short_answer';
  chapter_number?: number | null;
  chapter_title?: string | null;
  question: string;
  options?: string[] | null;
  marks: number;
}

export interface PaperSection {
  title: string;
  type: 'mcq' | 'short_answer';
  marks_each: number;
  questions: PaperQuestion[];
}

export interface ExamPaperView {
  exam_id: string;
  book: {
    id?: string;
    title?: string;
  };
  total_marks: number;
  difficulty?: string | null;
  language?: string | null;
  sections: PaperSection[];
}

export interface AnswerEntry {
  q_no: number;
  type: 'mcq' | 'short_answer';
  chapter_number?: number | null;
  marks: number;
  correct_index?: number | null;
  correct_option?: string | null;
  expected_answer?: string | null;
  explanation?: string | null;
}

export interface ExamAnswerKey {
  exam_id: string;
  total_marks: number;
  answers: AnswerEntry[];
}

export interface ExamPaperViewPayload {
  total_marks?: number;
  sections?: Array<{
    title?: string;
    type?: string;
    marks_each?: number;
    questions?: Array<Record<string, unknown>>;
  }>;
}

export interface ChatMessage {
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  contextFound?: boolean;
  usedDocuments?: string[];
}
