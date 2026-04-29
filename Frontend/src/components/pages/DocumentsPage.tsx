import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Clock, FileText, Loader2, Trash, Upload, Zap } from 'lucide-react';
import { apiService } from '../../services/api';
import { LooseDocument } from '../../types';

const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<LooseDocument[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [processingDocId, setProcessingDocId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void fetchDocs();
  }, []);

  useEffect(() => {
    const isAnyDocProcessing = documents.some((doc) => doc.status === 'processing');
    let interval: ReturnType<typeof setInterval>;

    if (isAnyDocProcessing) {
      interval = setInterval(() => {
        void fetchDocs();
      }, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [documents]);

  const fetchDocs = async () => {
    try {
      setError(null);
      const docs = await apiService.getLooseDocuments();
      setDocuments(docs);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load documents');
    }
  };

  const handleUpload = async (file?: File) => {
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      await apiService.uploadLooseDocument(file);
      await fetchDocs();
      setNotice(`"${file.name}" uploaded successfully. Process it before using it in chat.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to upload document');
    } finally {
      setIsUploading(false);
    }
  };

  const handleProcess = async (doc: LooseDocument) => {
    if (doc.status === 'processing') return;

    setProcessingDocId(doc.id);
    setError(null);
    try {
      const result = await apiService.processLooseDocument(doc.id);
      setDocuments((prev) =>
        prev.map(d => d.id === doc.id
          ? { ...d, ...result }
          : d
        )
      );
      await fetchDocs();
      setNotice(`Document "${doc.filename}" processed successfully.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to process document');
    } finally {
      setProcessingDocId(null);
    }
  };

  const handleDelete = async (doc: LooseDocument) => {
    if (!window.confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    setError(null);
    try {
      await apiService.deleteLooseDocument(doc.id);
      setDocuments((prev) => prev.filter((item) => item.id !== doc.id));
      setNotice(`Deleted "${doc.filename}".`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete document');
    }
  };

  const processedCount = useMemo(
    () => documents.filter((doc) => doc.is_processed).length,
    [documents]
  );

  const getDocStatus = (doc: LooseDocument) => {
    if (doc.status === 'failed') return 'failed';
    if (doc.status === 'processing' || processingDocId === doc.id) return 'processing';
    if (doc.is_processed || doc.status === 'completed') return 'processed';
    return 'pending';
  };

  return (
    <div className="space-y-6 relative">
      {error && (
        <div className="alert-error">
          <p className="text-sm text-error-700 dark:text-error-300">{error}</p>
        </div>
      )}
      {notice && (
        <div className="alert-success">
          <p className="text-sm text-success-700 dark:text-success-300">{notice}</p>
        </div>
      )}

      <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-lg rounded-2xl shadow-lg p-6 border border-white/20 dark:border-gray-700/20">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Loose Documents</h1>
            <div className="flex items-center gap-1.5 flex-wrap">
              {['Upload', 'Process', 'Query'].map((step, i, arr) => (
                <span key={step} className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                    {step}
                  </span>
                  {i < arr.length - 1 && (
                    <span className="text-gray-300 dark:text-gray-600 text-sm">→</span>
                  )}
                </span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {processedCount > 0 && (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-xl">
                <Zap className="h-3.5 w-3.5 text-blue-500" />
                <span className="text-xs font-semibold text-blue-700 dark:text-blue-300">{processedCount} processed</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-lg rounded-2xl shadow-lg p-6 border border-white/20 dark:border-gray-700/20">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Upload Document</h2>
        <label className="flex flex-col items-center justify-center w-full h-44 border-2 border-dashed border-blue-300 dark:border-blue-700/50 rounded-2xl cursor-pointer hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/10 transition-all bg-white dark:bg-gray-800/50 group">
          <div className="flex flex-col items-center justify-center">
            {isUploading ? (
              <Loader2 className="h-10 w-10 text-blue-500 animate-spin mb-3" />
            ) : (
              <div className="p-4 bg-blue-50 dark:bg-blue-900/30 rounded-2xl mb-3 group-hover:scale-110 transition-transform">
                <Upload className="h-8 w-8 text-blue-500 dark:text-blue-400" />
              </div>
            )}
            <p className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-1">
              {isUploading ? 'Uploading...' : 'Click to upload or drag & drop'}
            </p>
            <p className="text-xs text-gray-400">PDF, TXT, DOCX, MD, RTF, CSV, JSON, HTML (Max limit: 50MB)</p>
          </div>
          <input
            type="file"
            className="hidden"
            accept=".pdf,.txt,.doc,.docx,.md,.rtf,.csv,.json,.html"
            onChange={(e) => handleUpload(e.target.files?.[0])}
            disabled={isUploading}
          />
        </label>
      </div>

      <div className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-lg rounded-2xl shadow-lg p-6 border border-white/20 dark:border-gray-700/20">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">
          Uploaded Documents
          {documents.length > 0 && (
            <span className="ml-2 text-sm font-normal text-gray-400">({documents.length})</span>
          )}
        </h2>

        {documents.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 bg-gray-50 dark:bg-gray-700/50 rounded-full flex items-center justify-center mx-auto mb-4 border border-gray-100 dark:border-gray-700">
              <FileText className="h-8 w-8 text-gray-300 dark:text-gray-500" />
            </div>
            <p className="text-base font-medium text-gray-500 dark:text-gray-400 mb-1">No documents yet</p>
            <p className="text-sm text-gray-400">Upload your first document to get started</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {documents.map((doc) => {
              const status = getDocStatus(doc);
              return (
                <div
                  key={doc.id}
                  className={`relative flex flex-col p-5 rounded-2xl border transition-all ${status === 'processed'
                      ? 'border-blue-200 dark:border-blue-700/50 bg-blue-50/20 dark:bg-blue-900/5 hover:shadow-md'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600'
                    }`}
                >
                  <div className="absolute top-3 right-3 flex items-center gap-2">
                    {status === 'processed' && (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-blue-700 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/40 border border-blue-200 dark:border-blue-700/50 px-2 py-0.5 rounded-full uppercase tracking-wide">
                        <Zap className="h-2.5 w-2.5" /> Ready
                      </span>
                    )}
                    {status === 'processing' && (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-indigo-700 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-900/40 border border-indigo-200 dark:border-indigo-700/50 px-2 py-0.5 rounded-full uppercase tracking-wide">
                        <Loader2 className="h-2.5 w-2.5 animate-spin" /> Processing
                      </span>
                    )}
                    {status === 'failed' && (
                      <span
                        className="flex items-center gap-1 text-[10px] font-bold text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-900/40 border border-red-200 dark:border-red-700/50 px-2 py-0.5 rounded-full uppercase tracking-wide cursor-help"
                        title={doc.error_message || 'Processing failed'}
                      >
                        <AlertCircle className="h-2.5 w-2.5" /> Failed
                      </span>
                    )}
                    {status === 'pending' && (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-700/50 px-2 py-0.5 rounded-full uppercase tracking-wide">
                        <Clock className="h-2.5 w-2.5" /> Pending
                      </span>
                    )}
                  </div>

                  <div className="flex items-start gap-3 mb-4 pr-16 mt-2">
                    <div className={`p-2.5 rounded-xl flex-shrink-0 ${status === 'processed' ? 'bg-blue-100 dark:bg-blue-900/30'
                        : status === 'failed' ? 'bg-red-100 dark:bg-red-900/30'
                          : 'bg-gray-100 dark:bg-gray-700/50'
                      }`}>
                      <FileText className={`h-5 w-5 ${status === 'processed' ? 'text-blue-600 dark:text-blue-400'
                          : status === 'failed' ? 'text-red-500 dark:text-red-400'
                            : 'text-gray-400 dark:text-gray-500'
                        }`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 break-words line-clamp-2" title={doc.filename}>
                        {doc.filename}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {new Date(doc.created_at || Date.now()).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </p>
                    </div>
                  </div>

                  <div className="mt-auto flex flex-col gap-2 pt-3 border-t border-gray-100 dark:border-gray-700/60">
                    {status !== 'processed' && (
                      <button
                        onClick={() => handleProcess(doc)}
                        disabled={processingDocId === doc.id || status === 'processing'}
                        className={`w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold text-white rounded-lg transition-all shadow-sm ${status === 'failed'
                          ? 'bg-gradient-to-r from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600'
                          : 'bg-gradient-to-r from-indigo-500 to-blue-600 hover:from-indigo-600 hover:to-blue-700 disabled:opacity-60'
                          }`}
                      >
                        {processingDocId === doc.id || status === 'processing' ? (
                          <>
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Processing Background...
                          </>
                        ) : status === 'failed' ? (
                          <>
                            <AlertCircle className="h-3.5 w-3.5" />
                            Retry Processing
                          </>
                        ) : (
                          <>
                            <Zap className="h-3.5 w-3.5" />
                            Process Document
                          </>
                        )}
                      </button>
                    )}

                    <div className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500 dark:bg-gray-700/40 dark:text-gray-300">
                      <span className="truncate">ID: {doc.id}</span>
                      <button
                        onClick={() => handleDelete(doc)}
                        className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title="Delete"
                      >
                        <Trash className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentsPage;