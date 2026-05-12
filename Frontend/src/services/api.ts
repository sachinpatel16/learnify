import {
  APIEnvelope,
  Book,
  BookDetail,
  ChapterDocument,
  Exam,
  ExamAnswerKey,
  ExamPaperView,
  ExamSpec,
  Subject,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

class APIService {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const config: RequestInit = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      let errorMessage = 'API request failed';
      try {
        const error = await response.json();
        errorMessage = error.detail || error.message || errorMessage;
      } catch {
        // Ignore JSON parse failures and use generic error.
      }
      throw new Error(errorMessage);
    }

    const result: APIEnvelope<T> = await response.json();
    return result.data;
  }

  private async upload<T>(endpoint: string, formData: FormData): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      let errorMessage = 'Upload failed';
      try {
        const error = await response.json();
        errorMessage = error.detail || error.message || errorMessage;
      } catch {
        // Ignore JSON parse failures and use generic error.
      }
      throw new Error(errorMessage);
    }

    const result: APIEnvelope<T> = await response.json();
    return result.data;
  }

  async createBook(payload: {
    title: string;
    standard?: string;
    subject?: string;
    board?: string;
    language?: string;
  }): Promise<Book> {
    return this.request('/rag/books', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getBooks(subjectFilter?: string): Promise<Book[]> {
    const query = subjectFilter?.trim()
      ? `?subject=${encodeURIComponent(subjectFilter.trim())}`
      : '';
    return this.request(`/rag/books${query}`);
  }

  async getSubjects(): Promise<Subject[]> {
    return this.request('/rag/subjects');
  }

  async createSubject(payload: {
    name: string;
    standard?: string;
    board?: string;
    language?: string;
  }): Promise<Subject> {
    return this.request('/rag/subjects', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async updateSubject(
    subjectId: string,
    payload: {
      name?: string;
      standard?: string;
      board?: string;
      language?: string;
    }
  ): Promise<Subject> {
    return this.request(`/rag/subjects/${subjectId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  async deleteSubject(subjectId: string): Promise<null> {
    return this.request(`/rag/subjects/${subjectId}`, { method: 'DELETE' });
  }

  async getBook(bookId: string): Promise<BookDetail> {
    return this.request(`/rag/books/${bookId}`);
  }

  async deleteBook(bookId: string): Promise<null> {
    return this.request(`/rag/books/${bookId}`, { method: 'DELETE' });
  }

  async uploadChapter(
    bookId: string,
    payload: {
      file: File;
      chapter_number: number;
      chapter_title: string;
      display_name?: string;
    }
  ): Promise<ChapterDocument> {
    const formData = new FormData();
    formData.append('file', payload.file);
    formData.append('chapter_number', String(payload.chapter_number));
    formData.append('chapter_title', payload.chapter_title);
    if (payload.display_name?.trim()) {
      formData.append('display_name', payload.display_name.trim());
    }
    return this.upload(`/rag/books/${bookId}/chapters`, formData);
  }

  async getBookChapters(bookId: string): Promise<ChapterDocument[]> {
    return this.request(`/rag/books/${bookId}/chapters`);
  }

  async getBookExams(bookId: string): Promise<Exam[]> {
    return this.request(`/rag/books/${bookId}/exams`);
  }

  async processBookChapter(bookId: string, chapterId: string): Promise<ChapterDocument> {
    return this.request(`/rag/books/${bookId}/chapters/${chapterId}/process`, {
      method: 'POST',
    });
  }

  async createExam(spec: ExamSpec): Promise<Exam> {
    return this.request('/rag/exams', {
      method: 'POST',
      body: JSON.stringify(spec),
    });
  }

  async getExam(examId: string): Promise<Exam> {
    return this.request(`/rag/exams/${examId}`);
  }

  /** Long-poll exam status (server holds until completed/failed or timeout). */
  async waitExam(
    examId: string,
    options?: { timeout?: number; interval?: number }
  ): Promise<Exam> {
    const timeout = options?.timeout ?? 38;
    const interval = options?.interval ?? 1;
    const params = new URLSearchParams({
      timeout: String(timeout),
      interval: String(interval),
    });
    return this.request(`/rag/exams/${examId}/wait?${params.toString()}`);
  }

  async getExamPaper(examId: string): Promise<ExamPaperView> {
    return this.request(`/rag/exams/${examId}/paper`);
  }

  async getExamAnswerKey(examId: string): Promise<ExamAnswerKey> {
    return this.request(`/rag/exams/${examId}/answer-key`);
  }

  async deleteExam(examId: string): Promise<null> {
    return this.request(`/rag/exams/${examId}`, { method: 'DELETE' });
  }

  async pollExamUntilSettled(
    examId: string,
    onUpdate?: (exam: Exam) => void
  ): Promise<Exam> {
    let current = await this.getExam(examId);
    onUpdate?.(current);

    while (current.status === 'pending' || current.status === 'generating') {
      current = await this.waitExam(examId, { timeout: 38, interval: 1 });
      onUpdate?.(current);
    }

    if (current.status === 'failed') {
      throw new Error(current.error_message || 'Exam generation failed');
    }

    return current;
  }
}

export const apiService = new APIService();