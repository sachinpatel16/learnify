import React, { useEffect, useMemo, useState } from 'react';
import { BookOpen, Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { apiService } from '../../services/api';
import { Book } from '../../types';
import BookDetailPage from './BookDetailPage';

const defaultForm = {
  title: '',
  standard: '',
  subject: '',
  board: '',
  language: 'en',
};

const BooksPage: React.FC = () => {
  const [books, setBooks] = useState<Book[]>([]);
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);
  const [form, setForm] = useState(defaultForm);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedBook = useMemo(
    () => books.find((book) => book.id === selectedBookId) ?? null,
    [books, selectedBookId]
  );

  const loadBooks = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiService.getBooks();
      setBooks(result);
      setSelectedBookId((current) => {
        if (current && result.some((book) => book.id === current)) {
          return current;
        }
        return result[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load books');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadBooks();
  }, []);

  const handleCreateBook = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.title.trim()) return;

    setSubmitting(true);
    setError(null);
    try {
      const created = await apiService.createBook({
        title: form.title.trim(),
        standard: form.standard.trim() || undefined,
        subject: form.subject.trim() || undefined,
        board: form.board.trim() || undefined,
        language: form.language.trim() || 'en',
      });
      setBooks((current) => [created, ...current]);
      setSelectedBookId(created.id);
      setForm(defaultForm);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create book');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteBook = async (book: Book) => {
    if (!window.confirm(`Delete "${book.title}" and all its chapters/exams?`)) {
      return;
    }

    setDeletingId(book.id);
    setError(null);
    try {
      await apiService.deleteBook(book.id);
      setBooks((current) => current.filter((item) => item.id !== book.id));
      setSelectedBookId((current) => (current === book.id ? null : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete book');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card-glass">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Books & Exams</h1>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              Create books, upload chapter files, and generate student papers with answer keys.
            </p>
          </div>
          <button onClick={() => void loadBooks()} className="btn-secondary flex items-center gap-2" type="button">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="alert-error">
          <p className="text-sm text-error-700 dark:text-error-300">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-6">
          <section className="card">
            <div className="mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5 text-primary-600 dark:text-primary-400" />
              <h2 className="text-lg font-semibold">Create Book</h2>
            </div>

            <form className="space-y-3" onSubmit={handleCreateBook}>
              <input
                className="input-field"
                placeholder="Book title"
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                required
              />
              <input
                className="input-field"
                placeholder="Standard (optional)"
                value={form.standard}
                onChange={(event) => setForm((current) => ({ ...current, standard: event.target.value }))}
              />
              <input
                className="input-field"
                placeholder="Subject (optional)"
                value={form.subject}
                onChange={(event) => setForm((current) => ({ ...current, subject: event.target.value }))}
              />
              <input
                className="input-field"
                placeholder="Board (optional)"
                value={form.board}
                onChange={(event) => setForm((current) => ({ ...current, board: event.target.value }))}
              />
              <input
                className="input-field"
                placeholder="Language"
                value={form.language}
                onChange={(event) => setForm((current) => ({ ...current, language: event.target.value }))}
              />
              <button className="btn-primary w-full" disabled={submitting} type="submit">
                {submitting ? 'Creating...' : 'Create Book'}
              </button>
            </form>
          </section>

          <section className="card">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">Available Books</h2>
              <span className="text-sm text-gray-500 dark:text-gray-400">{books.length}</span>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-12 text-gray-500 dark:text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            ) : books.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-300 px-4 py-10 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
                No books yet. Create your first book to start uploading chapters.
              </div>
            ) : (
              <div className="space-y-3">
                {books.map((book) => {
                  const isSelected = selectedBookId === book.id;
                  return (
                    <div
                      key={book.id}
                      className={`rounded-xl border p-4 transition ${
                        isSelected
                          ? 'border-primary-500 bg-primary-50 dark:border-primary-400 dark:bg-primary-900/20'
                          : 'border-gray-200 bg-white dark:border-white/10 dark:bg-[#0f0f0f]'
                      }`}
                    >
                      <button
                        className="w-full text-left"
                        onClick={() => setSelectedBookId(book.id)}
                        type="button"
                      >
                        <div className="flex items-start gap-3">
                          <div className="rounded-lg bg-primary-100 p-2 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
                            <BookOpen className="h-4 w-4" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="font-semibold text-gray-900 dark:text-white">{book.title}</p>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              {[book.standard, book.subject, book.board, book.language].filter(Boolean).join(' | ') || 'No metadata'}
                            </p>
                          </div>
                        </div>
                      </button>

                      <div className="mt-3 flex justify-end">
                        <button
                          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                          disabled={deletingId === book.id}
                          onClick={() => void handleDeleteBook(book)}
                          type="button"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          {deletingId === book.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>

        <div>
          {selectedBook ? (
            <BookDetailPage bookId={selectedBook.id} onBookUpdated={() => void loadBooks()} />
          ) : (
            <div className="card flex min-h-[420px] items-center justify-center text-center">
              <div>
                <BookOpen className="mx-auto mb-4 h-12 w-12 text-gray-300 dark:text-gray-600" />
                <p className="text-lg font-semibold text-gray-700 dark:text-gray-200">Select a book</p>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                  Choose a book from the list to upload chapters and generate exams.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BooksPage;
