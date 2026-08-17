import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { expenseAPI } from '../utils/api';
import Layout from '../components/Layout';

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB, mirrors backend MAX_CONTENT_LENGTH

const ACCEPTED_EXTENSIONS = ['.csv', '.pdf'];

/**
 * Bank-statement upload page: drag-and-drop a CSV or PDF export, see
 * parse/categorize results, and browse recent upload history.
 */
const UploadPage = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [uploads, setUploads] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await expenseAPI.getUploads();
      setUploads(response.data.data || []);
    } catch (err) {
      // Non-fatal - history is a nice-to-have on this page
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const validateAndSetFile = (file) => {
    setError(null);
    setResult(null);

    if (!file) return;

    const lowerName = file.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
      setError('Only .csv and .pdf files are supported.');
      return;
    }
    if (file.size === 0) {
      setError('This file is empty.');
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setError('File is too large. Maximum upload size is 10MB.');
      return;
    }
    setSelectedFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    validateAndSetFile(file);
  };

  const handleFileSelect = (e) => {
    validateAndSetFile(e.target.files?.[0]);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setUploading(true);
    setError(null);
    setResult(null);
    setSessionExpired(false);
    setProgress(0);

    try {
      const response = await expenseAPI.uploadCSV(selectedFile, (evt) => {
        if (evt.total) {
          setProgress(Math.round((evt.loaded * 100) / evt.total));
        }
      });
      setResult(response.data.data);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      fetchHistory();
    } catch (err) {
      const status = err.response?.status;

      if (status === 401) {
        // Token expired mid-upload: keep the file staged and let the user
        // decide when to re-authenticate, instead of forcing a redirect.
        setSessionExpired(true);
      } else if (status === 422) {
        setError(err.response?.data?.details || err.response?.data?.error || 'Could not parse this file.');
      } else if (status === 413) {
        setError('File is too large. Maximum upload size is 10MB.');
      } else {
        setError(err.response?.data?.error || 'Upload failed. Please try again.');
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <Layout>
      <div className="max-w-4xl mx-auto">
        <div className="mb-6 sm:mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Upload Bank Statement</h1>
          <p className="text-gray-500 mt-1 text-sm sm:text-base">
            Drag in a CSV or PDF export from your bank to parse, categorize, and de-duplicate it automatically.
          </p>
        </div>

        {sessionExpired && (
          <div className="bg-yellow-50 border border-yellow-300 text-yellow-800 rounded-lg p-4 mb-6">
            <p className="font-semibold text-sm sm:text-base">Your session has expired.</p>
            <p className="text-sm mt-1">
              {selectedFile
                ? `"${selectedFile.name}" is still selected. Log in again, then come back to this page and click Upload to retry.`
                : 'Please log in again to continue.'}
            </p>
            <button
              onClick={() => navigate('/login')}
              className="mt-3 bg-yellow-600 hover:bg-yellow-700 text-white text-sm font-semibold py-1.5 px-4 rounded"
            >
              Log In Again
            </button>
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm p-4 sm:p-6 mb-6 sm:mb-8">
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-6 sm:p-12 text-center cursor-pointer transition ${
              isDragging ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300 hover:border-indigo-400'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.pdf"
              className="hidden"
              onChange={handleFileSelect}
            />
            <p className="text-gray-600 text-sm sm:text-lg break-all">
              {selectedFile ? selectedFile.name : 'Drag and drop your CSV or PDF statement here, or tap to browse'}
            </p>
            <p className="text-gray-400 text-xs sm:text-sm mt-2">CSV or PDF files, up to 10MB</p>
          </div>

          {error && (
            <div className="mt-4 bg-red-50 border border-red-300 text-red-700 rounded-lg p-4 text-sm">
              {error}
            </div>
          )}

          {uploading && (
            <div className="mt-4">
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div className="bg-indigo-600 h-2.5 rounded-full transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="text-sm text-gray-500 mt-1">Uploading... {progress}%</p>
            </div>
          )}

          {result && (
            <div className="mt-4 bg-green-50 border border-green-300 text-green-800 rounded-lg p-4">
              <p className="font-semibold text-sm sm:text-base">Upload complete</p>
              <ul className="text-sm mt-2 space-y-1">
                <li>{result.inserted} new transaction(s) added</li>
                {result.duplicates_skipped > 0 && (
                  <li>{result.duplicates_skipped} duplicate transaction(s) skipped</li>
                )}
              </ul>
              <Link to="/dashboard" className="inline-block mt-3 text-green-900 underline font-semibold text-sm sm:text-base">
                View on dashboard
              </Link>
            </div>
          )}

          <button
            onClick={handleUpload}
            disabled={!selectedFile || uploading}
            className="mt-6 w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition"
          >
            {uploading ? 'Uploading...' : 'Upload Statement'}
          </button>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-4 sm:p-6">
          <h2 className="text-lg sm:text-2xl font-bold text-gray-900 mb-3 sm:mb-4">Upload History</h2>
          {loadingHistory ? (
            <p className="text-gray-500 text-sm sm:text-base">Loading...</p>
          ) : uploads.length === 0 ? (
            <p className="text-gray-500 text-sm sm:text-base">No uploads yet.</p>
          ) : (
            <div className="overflow-x-auto -mx-4 sm:mx-0 px-4 sm:px-0">
              <table className="w-full min-w-[520px] text-sm">
                <thead>
                  <tr className="border-b-2 border-gray-200 text-left text-gray-700">
                    <th className="py-2 px-3">File</th>
                    <th className="py-2 px-3">Date</th>
                    <th className="py-2 px-3">Status</th>
                    <th className="py-2 px-3 text-right">Added</th>
                    <th className="py-2 px-3 text-right">Duplicates</th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.map((u) => (
                    <tr key={u.id} className="border-b border-gray-100">
                      <td className="py-2 px-3 text-gray-900 max-w-[160px] truncate">{u.filename}</td>
                      <td className="py-2 px-3 text-gray-600 whitespace-nowrap">
                        {new Date(u.upload_date).toLocaleString()}
                      </td>
                      <td className="py-2 px-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap ${
                          u.status === 'completed' ? 'bg-green-100 text-green-800' :
                          u.status === 'failed' ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {u.status}
                        </span>
                        {u.status === 'failed' && u.error_message && (
                          <p className="text-xs text-red-500 mt-1 max-w-[220px]">{u.error_message}</p>
                        )}
                        {u.status === 'completed' && u.error_message && (
                          <p className={`text-xs mt-1 max-w-[220px] ${
                            u.error_message.includes('lower-confidence') ? 'text-amber-600 font-medium' : 'text-blue-500'
                          }`}>
                            {u.error_message.includes('lower-confidence') ? '⚠️ ' : '✨ '}
                            {u.error_message.includes('lower-confidence') ? u.error_message : 'AI-assisted parse'}
                          </p>
                        )}
                      </td>
                      <td className="py-2 px-3 text-right">{u.parsed_count}</td>
                      <td className="py-2 px-3 text-right">{u.duplicate_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};

export default UploadPage;
