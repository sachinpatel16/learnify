import React, { useEffect, useMemo, useState } from 'react';
import { BookOpen, FileText, HelpCircle, KeyRound, Loader2 } from 'lucide-react';
import { apiService } from '../../services/api';
import { Book, Exam, ExamAnswerKey, ExamPaperView } from '../../types';

type ReaderTab = 'paper' | 'questions' | 'answers';

const ExamReaderPage: React.FC = () => {
  const [books, setBooks] = useState<Book[]>([]);
  const [exams, setExams] = useState<Exam[]>([]);
  const [selectedBookId, setSelectedBookId] = useState<string>('');
  const [selectedExamId, setSelectedExamId] = useState<string>('');
  const [examPaper, setExamPaper] = useState<ExamPaperView | null>(null);
  const [answerKey, setAnswerKey] = useState<ExamAnswerKey | null>(null);
  const [activeTab, setActiveTab] = useState<ReaderTab>('paper');
  const [booksLoading, setBooksLoading] = useState(true);
  const [examsLoading, setExamsLoading] = useState(false);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadBooks = async () => {
      setBooksLoading(true);
      setError(null);
      try {
        const result = await apiService.getBooks();
        setBooks(result);
        setSelectedBookId(result[0]?.id ?? '');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load books');
      } finally {
        setBooksLoading(false);
      }
    };

    void loadBooks();
  }, []);

  useEffect(() => {
    const loadExams = async () => {
      if (!selectedBookId) {
        setExams([]);
        setSelectedExamId('');
        return;
      }
      setExamsLoading(true);
      setError(null);
      try {
        const result = await apiService.getBookExams(selectedBookId);
        setExams(result);
        setSelectedExamId((current) => {
          if (current && result.some((exam) => exam.id === current)) {
            return current;
          }
          return result[0]?.id ?? '';
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load exams');
      } finally {
        setExamsLoading(false);
      }
    };

    void loadExams();
  }, [selectedBookId]);

  useEffect(() => {
    const loadArtifacts = async () => {
      if (!selectedExamId) {
        setExamPaper(null);
        setAnswerKey(null);
        return;
      }
      setArtifactsLoading(true);
      setError(null);
      try {
        const [paperRes, keyRes] = await Promise.allSettled([
          apiService.getExamPaper(selectedExamId),
          apiService.getExamAnswerKey(selectedExamId),
        ]);

        if (paperRes.status === 'fulfilled') {
          setExamPaper(paperRes.value);
        } else {
          setExamPaper(null);
        }

        if (keyRes.status === 'fulfilled') {
          setAnswerKey(keyRes.value);
        } else {
          setAnswerKey(null);
        }

        if (paperRes.status === 'rejected' && keyRes.status === 'rejected') {
          setError('Could not load paper or answer key for this exam yet.');
        }
      } finally {
        setArtifactsLoading(false);
      }
    };

    void loadArtifacts();
  }, [selectedExamId]);

  const flattenedQuestions = useMemo(() => {
    if (!examPaper) return [];
    return examPaper.sections.flatMap((section) =>
      section.questions.map((question) => ({
        ...question,
        sectionTitle: section.title,
      }))
    );
  }, [examPaper]);

  const getExamLabel = (exam: Exam): string => {
    const title = exam.title?.trim();
    const primary = title || `Exam ${exam.id.slice(0, 8)}`;
    return `${primary} (${exam.status})`;
  };

  return (
    <div className="space-y-6">
      <div className="card-glass">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Exam Reader</h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              Read generated exams in a clean view with dedicated Paper, Questions, and Answers tabs.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="alert-error">
          <p className="text-sm text-error-700 dark:text-error-300">{error}</p>
        </div>
      )}

      <section className="card space-y-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-gray-600 dark:text-gray-300">Select Book</span>
            <select
              className="input-field"
              value={selectedBookId}
              onChange={(event) => setSelectedBookId(event.target.value)}
              disabled={booksLoading}
            >
              {!books.length && <option value="">No books available</option>}
              {books.map((book) => (
                <option key={book.id} value={book.id}>
                  {book.title}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-gray-600 dark:text-gray-300">Select Exam</span>
            <select
              className="input-field"
              value={selectedExamId}
              onChange={(event) => setSelectedExamId(event.target.value)}
              disabled={examsLoading || !selectedBookId}
            >
              {!exams.length && <option value="">No exams available</option>}
              {exams.map((exam) => (
                <option key={exam.id} value={exam.id}>
                  {getExamLabel(exam)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="card">
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveTab('paper')}
            className={`btn-secondary px-3 py-1.5 text-xs ${activeTab === 'paper' ? 'ring-1 ring-primary-500' : ''}`}
          >
            <FileText className="mr-1 inline h-3.5 w-3.5" />
            Paper
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('questions')}
            className={`btn-secondary px-3 py-1.5 text-xs ${activeTab === 'questions' ? 'ring-1 ring-primary-500' : ''}`}
          >
            <HelpCircle className="mr-1 inline h-3.5 w-3.5" />
            Questions
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('answers')}
            className={`btn-secondary px-3 py-1.5 text-xs ${activeTab === 'answers' ? 'ring-1 ring-primary-500' : ''}`}
          >
            <KeyRound className="mr-1 inline h-3.5 w-3.5" />
            Answers
          </button>
        </div>

        {(booksLoading || examsLoading || artifactsLoading) && (
          <div className="flex items-center justify-center py-8 text-gray-500 dark:text-gray-400">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        )}

        {!booksLoading && !selectedBookId && (
          <p className="text-sm text-gray-500 dark:text-gray-400">No books found. Create a book and exam first.</p>
        )}

        {!booksLoading && selectedBookId && !selectedExamId && (
          <p className="text-sm text-gray-500 dark:text-gray-400">No exams found for this book yet.</p>
        )}

        {!artifactsLoading && selectedExamId && activeTab === 'paper' && (
          <div className="space-y-4">
            {!examPaper ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">Paper is not available for this exam yet.</p>
            ) : (
              examPaper.sections.map((section, sectionIndex) => (
                <section
                  key={`${section.title}-${sectionIndex}`}
                  className="rounded-xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#101010]"
                >
                  <p className="text-base font-semibold text-gray-900 dark:text-white">{section.title}</p>
                  <div className="mt-3 space-y-3">
                    {section.questions.map((question) => (
                      <article key={`${question.q_no}-${question.question}`} className="rounded-lg bg-gray-50 p-3 dark:bg-white/5">
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          Q{question.q_no}. {question.question}
                        </p>
                        {question.options && question.options.length > 0 && (
                          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-gray-600 dark:text-gray-300">
                            {question.options.map((option) => (
                              <li key={option}>{option}</li>
                            ))}
                          </ol>
                        )}
                      </article>
                    ))}
                  </div>
                </section>
              ))
            )}
          </div>
        )}

        {!artifactsLoading && selectedExamId && activeTab === 'questions' && (
          <div className="space-y-2">
            {!flattenedQuestions.length ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">No questions available.</p>
            ) : (
              flattenedQuestions.map((question) => (
                <article key={`${question.q_no}-${question.question}`} className="rounded-lg border border-gray-200 p-3 dark:border-white/10">
                  <p className="text-xs text-gray-500 dark:text-gray-400">{question.sectionTitle}</p>
                  <p className="mt-1 text-sm font-medium text-gray-900 dark:text-white">
                    Q{question.q_no}. {question.question}
                  </p>
                </article>
              ))
            )}
          </div>
        )}

        {!artifactsLoading && selectedExamId && activeTab === 'answers' && (
          <div className="space-y-2">
            {!answerKey || answerKey.answers.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">No answers available.</p>
            ) : (
              answerKey.answers.map((answer) => (
                <article key={`${answer.q_no}-${answer.type}`} className="rounded-lg border border-gray-200 p-3 dark:border-white/10">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    Q{answer.q_no} ({answer.type}) - {answer.marks} mark{answer.marks > 1 ? 's' : ''}
                  </p>
                  <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                    {answer.correct_option || answer.expected_answer || 'No answer data available'}
                  </p>
                  {answer.explanation && (
                    <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{answer.explanation}</p>
                  )}
                </article>
              ))
            )}
          </div>
        )}
      </section>

      <div className="rounded-lg border border-dashed border-gray-300 px-4 py-3 text-xs text-gray-500 dark:border-white/15 dark:text-gray-400">
        <BookOpen className="mr-1 inline h-3.5 w-3.5" />
        This reader is additive. Existing preview inside Books & Exams remains unchanged.
      </div>
    </div>
  );
};

export default ExamReaderPage;
