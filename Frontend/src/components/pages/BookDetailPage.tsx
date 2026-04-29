import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  Download,
  Eye,
  FileText,
  Loader2,
  Printer,
  RefreshCw,
  Sparkles,
  Upload,
} from 'lucide-react';
import { apiService } from '../../services/api';
import {
  BookDetail,
  ChapterDocument,
  Exam,
  ExamAnswerKey,
  ExamPaperView,
  ExamSectionInput,
} from '../../types';

const escapeHtml = (value: unknown) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const triggerDownload = (filename: string, content: string, mimeType: string) => {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000);
};

const buildPaperHtml = (paper: ExamPaperView): string => {
  const sectionsHtml = paper.sections
    .map((section) => {
      const questionsHtml = section.questions
        .map((question) => {
          const optionsHtml = question.options && question.options.length
            ? `<ol type="A" class="options">${question.options
                .map((option) => `<li>${escapeHtml(option)}</li>`)
                .join('')}</ol>`
            : '';
          const meta = [
            question.chapter_number ? `Chapter ${question.chapter_number}` : null,
            question.chapter_title || null,
            `${question.marks} mark${question.marks > 1 ? 's' : ''}`,
          ]
            .filter(Boolean)
            .join(' &middot; ');
          return `
            <div class="question">
              <p class="q"><strong>Q${question.q_no}.</strong> ${escapeHtml(question.question)}</p>
              ${meta ? `<p class="meta">${meta}</p>` : ''}
              ${optionsHtml}
            </div>
          `;
        })
        .join('');
      return `
        <section class="exam-section">
          <h2>${escapeHtml(section.title)}</h2>
          ${questionsHtml}
        </section>
      `;
    })
    .join('');

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(paper.book?.title || 'Exam Paper')}</title>
    <style>
      body { font-family: 'Segoe UI', Arial, sans-serif; color: #111; padding: 32px; max-width: 880px; margin: 0 auto; }
      h1 { margin-bottom: 4px; }
      h2 { margin-top: 28px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
      .meta { color: #555; font-size: 12px; margin: 0 0 8px 0; }
      .summary { color: #444; font-size: 14px; margin-bottom: 24px; }
      .question { margin: 14px 0; }
      .q { margin: 0 0 4px 0; }
      .options { margin: 6px 0 0 24px; padding: 0; }
      .options li { margin: 4px 0; }
      @media print { body { padding: 12px; } }
    </style>
  </head>
  <body>
    <h1>${escapeHtml(paper.book?.title || 'Exam Paper')}</h1>
    <p class="summary">
      Total Marks: <strong>${paper.total_marks}</strong>
      ${paper.difficulty ? ` &middot; Difficulty: ${escapeHtml(paper.difficulty)}` : ''}
      ${paper.language ? ` &middot; Language: ${escapeHtml(paper.language)}` : ''}
    </p>
    ${sectionsHtml}
  </body>
</html>`;
};

const buildAnswerKeyHtml = (answerKey: ExamAnswerKey): string => {
  const rows = answerKey.answers
    .map((answer) => {
      const correct =
        answer.correct_option || answer.expected_answer || 'Not provided';
      return `
        <tr>
          <td>Q${answer.q_no}</td>
          <td>${escapeHtml(answer.type)}</td>
          <td>${answer.chapter_number ?? '-'}</td>
          <td>${answer.marks}</td>
          <td>${escapeHtml(correct)}</td>
          <td>${escapeHtml(answer.explanation || '')}</td>
        </tr>
      `;
    })
    .join('');

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Answer Key</title>
    <style>
      body { font-family: 'Segoe UI', Arial, sans-serif; color: #111; padding: 32px; max-width: 960px; margin: 0 auto; }
      h1 { margin-bottom: 4px; }
      table { width: 100%; border-collapse: collapse; margin-top: 18px; font-size: 13px; }
      th, td { padding: 8px; border: 1px solid #cfcfcf; vertical-align: top; }
      th { background: #f4f4f5; text-align: left; }
      .summary { color: #444; font-size: 14px; }
      @media print { body { padding: 12px; } }
    </style>
  </head>
  <body>
    <h1>Answer Key</h1>
    <p class="summary">Total Marks: <strong>${answerKey.total_marks}</strong></p>
    <table>
      <thead>
        <tr>
          <th>Q.No</th>
          <th>Type</th>
          <th>Chapter</th>
          <th>Marks</th>
          <th>Correct / Expected</th>
          <th>Explanation</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </body>
</html>`;
};

const printHtml = (html: string) => {
  const printWindow = window.open('', '_blank');
  if (!printWindow) return;
  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  window.setTimeout(() => {
    try {
      printWindow.print();
    } catch {
      // User can still print manually if auto-print is blocked.
    }
  }, 400);
};

interface BookDetailPageProps {
  bookId: string;
  onBookUpdated: () => void;
}

const BookDetailPage: React.FC<BookDetailPageProps> = ({ bookId, onBookUpdated }) => {
  const [book, setBook] = useState<BookDetail | null>(null);
  const [exams, setExams] = useState<Exam[]>([]);
  const [selectedExamId, setSelectedExamId] = useState<string | null>(null);
  const [examPaper, setExamPaper] = useState<ExamPaperView | null>(null);
  const [answerKey, setAnswerKey] = useState<ExamAnswerKey | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploadingChapter, setUploadingChapter] = useState(false);
  const [generatingExam, setGeneratingExam] = useState(false);
  const [processingChapterId, setProcessingChapterId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [chapterFile, setChapterFile] = useState<File | null>(null);
  const [chapterNumber, setChapterNumber] = useState('');
  const [chapterTitle, setChapterTitle] = useState('');
  const [displayName, setDisplayName] = useState('');

  const [selectedChapters, setSelectedChapters] = useState<number[]>([]);
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium');
  const [distribution, setDistribution] = useState<'proportional' | 'evenly_split'>('proportional');
  const [sections, setSections] = useState<ExamSectionInput[]>([
    { type: 'mcq', count: 5, marks_each: 1 },
    { type: 'short_answer', count: 3, marks_each: 2 },
  ]);

  const selectedExam = useMemo(
    () => exams.find((exam) => exam.id === selectedExamId) ?? null,
    [exams, selectedExamId]
  );

  const loadBook = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [bookResult, examResult] = await Promise.all([
        apiService.getBook(bookId),
        apiService.getBookExams(bookId),
      ]);
      setBook(bookResult);
      setExams(examResult);
      setSelectedChapters((current) => {
        if (current.length > 0) return current;
        return bookResult.chapters
          .filter((chapter) => chapter.chapter_number != null)
          .slice(0, 2)
          .map((chapter) => Number(chapter.chapter_number));
      });
      setSelectedExamId((current) => {
        if (current && examResult.some((exam) => exam.id === current)) {
          return current;
        }
        return examResult[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load book details');
    } finally {
      setLoading(false);
    }
  }, [bookId]);

  useEffect(() => {
    setSelectedChapters([]);
    setSelectedExamId(null);
    void loadBook();
    setExamPaper(null);
    setAnswerKey(null);
  }, [bookId, loadBook]);

  const processChapter = async (chapter: ChapterDocument) => {
    setProcessingChapterId(chapter.id);
    setError(null);
    try {
      await apiService.processLooseDocument(chapter.id);
      await loadBook();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process chapter');
    } finally {
      setProcessingChapterId(null);
    }
  };

  const handleChapterUpload = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!chapterFile || !chapterNumber || !chapterTitle.trim()) return;

    setUploadingChapter(true);
    setError(null);
    try {
      await apiService.uploadChapter(bookId, {
        file: chapterFile,
        chapter_number: Number(chapterNumber),
        chapter_title: chapterTitle.trim(),
        display_name: displayName.trim() || undefined,
      });
      setChapterFile(null);
      setChapterNumber('');
      setChapterTitle('');
      setDisplayName('');
      await loadBook();
      onBookUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload chapter');
    } finally {
      setUploadingChapter(false);
    }
  };

  const updateSection = (index: number, patch: Partial<ExamSectionInput>) => {
    setSections((current) =>
      current.map((section, currentIndex) => (currentIndex === index ? { ...section, ...patch } : section))
    );
  };

  const addSection = () => {
    setSections((current) => [...current, { type: 'mcq', count: 1, marks_each: 1 }]);
  };

  const removeSection = (index: number) => {
    setSections((current) => current.filter((_, currentIndex) => currentIndex !== index));
  };

  const handleGenerateExam = async () => {
    if (!book || selectedChapters.length === 0) {
      setError('Select at least one processed chapter before generating an exam.');
      return;
    }

    setGeneratingExam(true);
    setError(null);
    setExamPaper(null);
    setAnswerKey(null);

    try {
      const created = await apiService.createExam({
        book_id: book.id,
        chapters: selectedChapters.sort((a, b) => a - b),
        sections,
        difficulty,
        language: book.language || 'en',
        standard: book.standard || undefined,
        subject: book.subject || undefined,
        per_chapter_distribution: distribution,
      });
      setSelectedExamId(created.id);
      const updatedExam = await apiService.pollExamUntilSettled(created.id, (current) => {
        setExams((existing) => {
          const others = existing.filter((exam) => exam.id !== current.id);
          return [current, ...others];
        });
      });
      setExams((existing) => {
        const others = existing.filter((exam) => exam.id !== updatedExam.id);
        return [updatedExam, ...others];
      });
      const [paper, key] = await Promise.all([
        apiService.getExamPaper(updatedExam.id),
        apiService.getExamAnswerKey(updatedExam.id),
      ]);
      setExamPaper(paper);
      setAnswerKey(key);
      await loadBook();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate exam');
    } finally {
      setGeneratingExam(false);
    }
  };

  const loadExamArtifacts = async (exam: Exam, target: 'paper' | 'answerKey' | 'both') => {
    setError(null);
    setSelectedExamId(exam.id);
    try {
      if (target === 'paper' || target === 'both') {
        const paper = await apiService.getExamPaper(exam.id);
        setExamPaper(paper);
      }
      if (target === 'answerKey' || target === 'both') {
        const key = await apiService.getExamAnswerKey(exam.id);
        setAnswerKey(key);
      }
      window.setTimeout(() => {
        document
          .getElementById('exam-preview-section')
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 50);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load exam data');
    }
  };

  if (loading) {
    return (
      <div className="card flex min-h-[420px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary-600 dark:text-primary-400" />
      </div>
    );
  }

  if (!book) {
    return (
      <div className="card">
        <p className="text-sm text-gray-500 dark:text-gray-400">Book details are unavailable.</p>
      </div>
    );
  }

  const processedChapters = book.chapters.filter((chapter) => chapter.is_processed && chapter.chapter_number != null);

  return (
    <div className="space-y-6">
      <div className="card-glass">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{book.title}</h2>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              {[book.standard, book.subject, book.board, book.language].filter(Boolean).join(' | ') || 'Book metadata not set'}
            </p>
          </div>
          <button className="btn-secondary flex items-center gap-2" onClick={() => void loadBook()} type="button">
            <RefreshCw className="h-4 w-4" />
            Reload
          </button>
        </div>
      </div>

      {error && (
        <div className="alert-error">
          <p className="text-sm text-error-700 dark:text-error-300">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <section className="card">
            <div className="mb-4 flex items-center gap-2">
              <Upload className="h-5 w-5 text-primary-600 dark:text-primary-400" />
              <h3 className="text-lg font-semibold">Upload Chapter</h3>
            </div>

            <form className="grid grid-cols-1 gap-3 md:grid-cols-2" onSubmit={handleChapterUpload}>
              <input
                className="input-field md:col-span-2"
                type="file"
                accept=".pdf,.csv,.txt,.doc,.docx,.md,.rtf,.json,.html"
                onChange={(event) => setChapterFile(event.target.files?.[0] ?? null)}
                required
              />
              <input
                className="input-field"
                placeholder="Chapter number"
                type="number"
                min={1}
                value={chapterNumber}
                onChange={(event) => setChapterNumber(event.target.value)}
                required
              />
              <input
                className="input-field"
                placeholder="Chapter title"
                value={chapterTitle}
                onChange={(event) => setChapterTitle(event.target.value)}
                required
              />
              <input
                className="input-field md:col-span-2"
                placeholder="Display name (optional)"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
              <button className="btn-primary md:col-span-2" disabled={uploadingChapter} type="submit">
                {uploadingChapter ? 'Uploading chapter...' : 'Upload Chapter'}
              </button>
            </form>
          </section>

          <section className="card">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-lg font-semibold">Chapters</h3>
              <span className="text-sm text-gray-500 dark:text-gray-400">{book.chapters.length}</span>
            </div>

            {book.chapters.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">No chapters uploaded yet.</p>
            ) : (
              <div className="space-y-3">
                {book.chapters.map((chapter) => {
                  const isSelectable = chapter.is_processed && chapter.chapter_number != null;
                  const isChecked = chapter.chapter_number != null && selectedChapters.includes(chapter.chapter_number);
                  return (
                    <div
                      key={chapter.id}
                      className="rounded-xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#0f0f0f]"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex min-w-0 items-start gap-3">
                          <input
                            checked={isChecked}
                            className="mt-1 h-4 w-4"
                            disabled={!isSelectable}
                            onChange={(event) => {
                              const value = Number(chapter.chapter_number);
                              setSelectedChapters((current) =>
                                event.target.checked
                                  ? [...new Set([...current, value])]
                                  : current.filter((item) => item !== value)
                              );
                            }}
                            type="checkbox"
                          />
                          <div>
                            <p className="font-semibold text-gray-900 dark:text-white">
                              {chapter.display_name || `Chapter ${chapter.chapter_number ?? '-'}`}
                            </p>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              File: {chapter.filename}
                            </p>
                            {chapter.error_message && (
                              <p className="mt-2 text-xs text-red-600 dark:text-red-400">{chapter.error_message}</p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <span
                            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                              chapter.status === 'completed'
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                : chapter.status === 'failed'
                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                                  : chapter.status === 'processing'
                                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                                    : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                            }`}
                          >
                            {chapter.status}
                          </span>
                          {!chapter.is_processed && (
                            <button
                              className="btn-secondary px-3 py-1.5 text-xs"
                              disabled={processingChapterId === chapter.id}
                              onClick={() => void processChapter(chapter)}
                              type="button"
                            >
                              {processingChapterId === chapter.id ? 'Processing...' : 'Process'}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="card">
            <div className="mb-4 flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary-600 dark:text-primary-400" />
              <h3 className="text-lg font-semibold">Generate Exam</h3>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="text-sm">
                <span className="mb-1 block text-gray-600 dark:text-gray-300">Difficulty</span>
                <select
                  className="input-field"
                  value={difficulty}
                  onChange={(event) => setDifficulty(event.target.value as 'easy' | 'medium' | 'hard')}
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-gray-600 dark:text-gray-300">Distribution</span>
                <select
                  className="input-field"
                  value={distribution}
                  onChange={(event) => setDistribution(event.target.value as 'proportional' | 'evenly_split')}
                >
                  <option value="proportional">Proportional</option>
                  <option value="evenly_split">Evenly split</option>
                </select>
              </label>
            </div>

            <div className="mt-4 space-y-3">
              {sections.map((section, index) => (
                <div key={`${section.type}-${index}`} className="grid grid-cols-1 gap-3 rounded-xl border border-gray-200 p-4 md:grid-cols-4 dark:border-white/10">
                  <select
                    className="input-field"
                    value={section.type}
                    onChange={(event) => updateSection(index, { type: event.target.value as 'mcq' | 'short_answer' })}
                  >
                    <option value="mcq">MCQ</option>
                    <option value="short_answer">Short answer</option>
                  </select>
                  <input
                    className="input-field"
                    min={1}
                    type="number"
                    value={section.count}
                    onChange={(event) => updateSection(index, { count: Number(event.target.value) })}
                  />
                  <input
                    className="input-field"
                    min={1}
                    type="number"
                    value={section.marks_each}
                    onChange={(event) => updateSection(index, { marks_each: Number(event.target.value) })}
                  />
                  <button
                    className="btn-secondary"
                    disabled={sections.length === 1}
                    onClick={() => removeSection(index)}
                    type="button"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <button className="btn-secondary" onClick={addSection} type="button">
                Add Section
              </button>
              <button
                className="btn-primary flex items-center gap-2"
                disabled={generatingExam || processedChapters.length === 0}
                onClick={() => void handleGenerateExam()}
                type="button"
              >
                {generatingExam ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {generatingExam ? 'Generating exam...' : 'Generate Exam'}
              </button>
            </div>

            <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
              Only processed chapters can be included in the exam request.
            </p>
          </section>
        </div>

        <div className="space-y-6">
          <section className="card">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-lg font-semibold">Generated Exams</h3>
              <span className="text-sm text-gray-500 dark:text-gray-400">{exams.length}</span>
            </div>

            {exams.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">No exams generated yet.</p>
            ) : (
              <div className="space-y-3">
                {exams.map((exam) => (
                  <div
                    key={exam.id}
                    className={`rounded-xl border p-4 ${
                      exam.id === selectedExamId
                        ? 'border-primary-500 bg-primary-50 dark:border-primary-400 dark:bg-primary-900/20'
                        : 'border-gray-200 dark:border-white/10'
                    }`}
                  >
                    <button
                      className="w-full text-left"
                      onClick={() => setSelectedExamId(exam.id)}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-gray-900 dark:text-white">{exam.id}</p>
                          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                            Total marks: {exam.total_marks || 0}
                          </p>
                        </div>
                        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700 dark:bg-white/10 dark:text-gray-300">
                          {exam.status}
                        </span>
                      </div>
                    </button>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <button className="btn-secondary px-3 py-1.5 text-xs" onClick={() => void loadExamArtifacts(exam, 'paper')} type="button">
                        <Eye className="mr-1 inline h-3.5 w-3.5" />
                        Paper
                      </button>
                      <button
                        className="btn-secondary px-3 py-1.5 text-xs"
                        onClick={() => void loadExamArtifacts(exam, 'answerKey')}
                        type="button"
                      >
                        <CheckCircle2 className="mr-1 inline h-3.5 w-3.5" />
                        Answer Key
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="card" id="exam-preview-section">
            <div className="mb-4 flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary-600 dark:text-primary-400" />
              <h3 className="text-lg font-semibold">Selected Exam Preview</h3>
            </div>

            {selectedExam && (
              <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
                Selected exam status: <span className="font-medium">{selectedExam.status}</span>
              </p>
            )}

            {!examPaper && !answerKey && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Click <span className="font-medium">Paper</span> or <span className="font-medium">Answer Key</span> on a completed exam to load it.
              </p>
            )}

            {examPaper && (
              <div className="mb-6 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-gray-50 p-4 dark:bg-white/5">
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      Paper - Total Marks: {examPaper.total_marks}
                    </p>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {examPaper.book?.title || 'Exam paper'}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="btn-secondary flex items-center gap-1.5 px-3 py-1.5 text-xs"
                      onClick={() => printHtml(buildPaperHtml(examPaper))}
                      type="button"
                    >
                      <Printer className="h-3.5 w-3.5" />
                      Print / Save as PDF
                    </button>
                    <button
                      className="btn-primary flex items-center gap-1.5 px-3 py-1.5 text-xs"
                      onClick={() =>
                        triggerDownload(
                          `exam-${examPaper.exam_id}-paper.html`,
                          buildPaperHtml(examPaper),
                          'text/html'
                        )
                      }
                      type="button"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download HTML
                    </button>
                  </div>
                </div>

                {examPaper.sections.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    The generator returned an empty paper. Try generating again.
                  </p>
                ) : (
                  examPaper.sections.map((section, sectionIndex) => (
                    <div
                      key={`${section.title}-${sectionIndex}`}
                      className="rounded-xl border border-gray-200 p-4 dark:border-white/10"
                    >
                      <p className="font-semibold text-gray-900 dark:text-white">{section.title}</p>
                      <div className="mt-3 space-y-3">
                        {section.questions.map((question) => (
                          <div
                            key={`${question.q_no}-${question.question}`}
                            className="rounded-lg bg-gray-50 p-3 dark:bg-white/5"
                          >
                            <p className="text-sm font-medium text-gray-900 dark:text-white">
                              Q{question.q_no}. {question.question}
                            </p>
                            {question.options && question.options.length > 0 && (
                              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-600 dark:text-gray-300">
                                {question.options.map((option) => (
                                  <li key={option}>{option}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {answerKey && (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-gray-50 p-4 dark:bg-white/5">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">
                    Answer Key - Total Marks: {answerKey.total_marks}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="btn-secondary flex items-center gap-1.5 px-3 py-1.5 text-xs"
                      onClick={() => printHtml(buildAnswerKeyHtml(answerKey))}
                      type="button"
                    >
                      <Printer className="h-3.5 w-3.5" />
                      Print / Save as PDF
                    </button>
                    <button
                      className="btn-primary flex items-center gap-1.5 px-3 py-1.5 text-xs"
                      onClick={() =>
                        triggerDownload(
                          `exam-${answerKey.exam_id}-answer-key.html`,
                          buildAnswerKeyHtml(answerKey),
                          'text/html'
                        )
                      }
                      type="button"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download HTML
                    </button>
                  </div>
                </div>

                {answerKey.answers.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    No answers in this exam yet.
                  </p>
                ) : (
                  answerKey.answers.map((answer) => (
                    <div
                      key={`${answer.q_no}-${answer.type}`}
                      className="rounded-xl border border-gray-200 p-4 dark:border-white/10"
                    >
                      <p className="font-medium text-gray-900 dark:text-white">
                        Q{answer.q_no} ({answer.type})
                      </p>
                      <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                        {answer.correct_option || answer.expected_answer || 'No answer data available'}
                      </p>
                      {answer.explanation && (
                        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{answer.explanation}</p>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default BookDetailPage;
