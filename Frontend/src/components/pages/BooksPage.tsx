import React, { useEffect, useMemo, useState } from 'react';
import { BookOpen, Loader2, Pencil, Plus, RefreshCw, Save, Trash2, X } from 'lucide-react';
import { apiService } from '../../services/api';
import { Book, Subject } from '../../types';
import BookDetailPage from './BookDetailPage';

const defaultForm = {
  title: '',
  standard: '',
  subject: '',
  board: '',
  language: 'en',
  selectedSubjectId: '',
  customSubject: '',
};

const BooksPage: React.FC = () => {
  const [books, setBooks] = useState<Book[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);
  const [subjectFilter, setSubjectFilter] = useState<string>('all');
  const [form, setForm] = useState(defaultForm);
  const [loading, setLoading] = useState(true);
  const [subjectsLoading, setSubjectsLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [subjectSubmitting, setSubjectSubmitting] = useState(false);
  const [subjectDeletingId, setSubjectDeletingId] = useState<string | null>(null);
  const [editingSubjectId, setEditingSubjectId] = useState<string | null>(null);
  const [editingSubjectForm, setEditingSubjectForm] = useState({
    name: '',
    standard: '',
    board: '',
    language: 'en',
  });
  const [newSubjectForm, setNewSubjectForm] = useState({
    name: '',
    standard: '',
    board: '',
    language: 'en',
  });
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedBook = useMemo(
    () => books.find((book) => book.id === selectedBookId) ?? null,
    [books, selectedBookId]
  );

  const loadBooks = async (filterValue: string = subjectFilter) => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiService.getBooks(filterValue === 'all' ? undefined : filterValue);
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

  const loadSubjects = async () => {
    setSubjectsLoading(true);
    try {
      const result = await apiService.getSubjects();
      setSubjects(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load subjects');
    } finally {
      setSubjectsLoading(false);
    }
  };

  useEffect(() => {
    void loadBooks();
    void loadSubjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadBooks(subjectFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectFilter]);

  const handleCreateBook = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.title.trim()) return;

    setSubmitting(true);
    setError(null);
    try {
      const created = await apiService.createBook({
        title: form.title.trim(),
        standard: form.standard.trim() || undefined,
        subject:
          form.customSubject.trim() ||
          subjects.find((subject) => subject.id === form.selectedSubjectId)?.name ||
          form.subject.trim() ||
          undefined,
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

  const handleCreateSubject = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!newSubjectForm.name.trim()) return;
    setSubjectSubmitting(true);
    setError(null);
    try {
      await apiService.createSubject({
        name: newSubjectForm.name.trim(),
        standard: newSubjectForm.standard.trim() || undefined,
        board: newSubjectForm.board.trim() || undefined,
        language: newSubjectForm.language.trim() || 'en',
      });
      setNewSubjectForm({ name: '', standard: '', board: '', language: 'en' });
      await loadSubjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create subject');
    } finally {
      setSubjectSubmitting(false);
    }
  };

  const startEditSubject = (subject: Subject) => {
    setEditingSubjectId(subject.id);
    setEditingSubjectForm({
      name: subject.name,
      standard: subject.standard ?? '',
      board: subject.board ?? '',
      language: subject.language ?? 'en',
    });
  };

  const handleUpdateSubject = async (subjectId: string) => {
    if (!editingSubjectForm.name.trim()) return;
    setSubjectSubmitting(true);
    setError(null);
    try {
      await apiService.updateSubject(subjectId, {
        name: editingSubjectForm.name.trim(),
        standard: editingSubjectForm.standard.trim() || undefined,
        board: editingSubjectForm.board.trim() || undefined,
        language: editingSubjectForm.language.trim() || undefined,
      });
      setEditingSubjectId(null);
      await Promise.all([loadSubjects(), loadBooks(subjectFilter)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update subject');
    } finally {
      setSubjectSubmitting(false);
    }
  };

  const handleDeleteSubject = async (subject: Subject) => {
    if (!window.confirm(`Delete subject "${subject.name}"?`)) return;
    setSubjectDeletingId(subject.id);
    setError(null);
    try {
      await apiService.deleteSubject(subject.id);
      if (subjectFilter === subject.id || subjectFilter === subject.name) {
        setSubjectFilter('all');
      }
      await Promise.all([loadSubjects(), loadBooks(subjectFilter)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete subject');
    } finally {
      setSubjectDeletingId(null);
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

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
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
            <select
              className="input-field"
              value={form.selectedSubjectId}
              onChange={(event) => setForm((current) => ({ ...current, selectedSubjectId: event.target.value }))}
            >
              <option value="">Select managed subject (optional)</option>
              {subjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </select>
            <input
              className="input-field"
              placeholder="Or type custom subject (optional)"
              value={form.customSubject}
              onChange={(event) => setForm((current) => ({ ...current, customSubject: event.target.value }))}
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
            <h2 className="text-lg font-semibold">Book List</h2>
            <span className="text-sm text-gray-500 dark:text-gray-400">{books.length}</span>
          </div>
          <select
            className="input-field mb-4"
            value={subjectFilter}
            onChange={(event) => setSubjectFilter(event.target.value)}
          >
            <option value="all">All subjects</option>
            {subjects.map((subject) => (
              <option key={subject.id} value={subject.id}>
                {subject.name}
              </option>
            ))}
          </select>

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
                    <button className="w-full text-left" onClick={() => setSelectedBookId(book.id)} type="button">
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

        <section className="card">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Subject Management</h2>
            <span className="text-sm text-gray-500 dark:text-gray-400">{subjects.length}</span>
          </div>

          <form className="space-y-2" onSubmit={handleCreateSubject}>
            <input
              className="input-field"
              placeholder="Subject name"
              value={newSubjectForm.name}
              onChange={(event) => setNewSubjectForm((current) => ({ ...current, name: event.target.value }))}
              required
            />
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              <input
                className="input-field"
                placeholder="Standard"
                value={newSubjectForm.standard}
                onChange={(event) => setNewSubjectForm((current) => ({ ...current, standard: event.target.value }))}
              />
              <input
                className="input-field"
                placeholder="Board"
                value={newSubjectForm.board}
                onChange={(event) => setNewSubjectForm((current) => ({ ...current, board: event.target.value }))}
              />
              <input
                className="input-field"
                placeholder="Language"
                value={newSubjectForm.language}
                onChange={(event) => setNewSubjectForm((current) => ({ ...current, language: event.target.value }))}
              />
            </div>
            <button className="btn-primary w-full" disabled={subjectSubmitting} type="submit">
              {subjectSubmitting ? 'Saving...' : 'Add Subject'}
            </button>
          </form>

          <div className="mt-4 space-y-2">
            {subjectsLoading ? (
              <div className="flex items-center justify-center py-6 text-gray-500 dark:text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            ) : subjects.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">No subjects added yet.</p>
            ) : (
              subjects.map((subject) => {
                const isEditing = editingSubjectId === subject.id;
                return (
                  <div key={subject.id} className="rounded-lg border border-gray-200 p-3 dark:border-white/10">
                    {isEditing ? (
                      <div className="space-y-2">
                        <input
                          className="input-field"
                          value={editingSubjectForm.name}
                          onChange={(event) => setEditingSubjectForm((current) => ({ ...current, name: event.target.value }))}
                        />
                        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                          <input
                            className="input-field"
                            placeholder="Standard"
                            value={editingSubjectForm.standard}
                            onChange={(event) => setEditingSubjectForm((current) => ({ ...current, standard: event.target.value }))}
                          />
                          <input
                            className="input-field"
                            placeholder="Board"
                            value={editingSubjectForm.board}
                            onChange={(event) => setEditingSubjectForm((current) => ({ ...current, board: event.target.value }))}
                          />
                          <input
                            className="input-field"
                            placeholder="Language"
                            value={editingSubjectForm.language}
                            onChange={(event) => setEditingSubjectForm((current) => ({ ...current, language: event.target.value }))}
                          />
                        </div>
                        <div className="flex justify-end gap-2">
                          <button className="btn-secondary px-3 py-1.5 text-xs" onClick={() => setEditingSubjectId(null)} type="button">
                            <X className="h-3.5 w-3.5" />
                          </button>
                          <button
                            className="btn-primary px-3 py-1.5 text-xs"
                            disabled={subjectSubmitting}
                            onClick={() => void handleUpdateSubject(subject.id)}
                            type="button"
                          >
                            <Save className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="font-medium text-gray-900 dark:text-white">{subject.name}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {[subject.standard, subject.board, subject.language].filter(Boolean).join(' | ') || 'No metadata'}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button className="btn-secondary px-2 py-1.5 text-xs" onClick={() => startEditSubject(subject)} type="button">
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            className="btn-secondary px-2 py-1.5 text-xs text-red-500"
                            disabled={subjectDeletingId === subject.id}
                            onClick={() => void handleDeleteSubject(subject)}
                            type="button"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </section>
      </div>

      <div>
        {selectedBook ? (
          <BookDetailPage bookId={selectedBook.id} onBookUpdated={() => void loadBooks(subjectFilter)} />
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
  );
};

export default BooksPage;
