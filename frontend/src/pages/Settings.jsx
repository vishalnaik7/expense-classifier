import React from 'react';
import Layout from '../components/Layout';
import useAuthStore from '../store/authStore';

const SettingsPage = () => {
  const user = useAuthStore((state) => state.user);

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1 text-sm">Your account details</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-5 max-w-lg">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-14 h-14 rounded-full bg-indigo-500 flex items-center justify-center text-white font-bold text-xl">
            {(user?.username || '?').charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="font-bold text-gray-900">{user?.username}</p>
            <p className="text-sm text-gray-500">{user?.email}</p>
          </div>
        </div>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between border-b border-gray-50 pb-2">
            <span className="text-gray-500">Username</span>
            <span className="text-gray-900 font-medium">{user?.username}</span>
          </div>
          <div className="flex justify-between border-b border-gray-50 pb-2">
            <span className="text-gray-500">Email</span>
            <span className="text-gray-900 font-medium">{user?.email}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Member since</span>
            <span className="text-gray-900 font-medium">
              {user?.created_at ? new Date(user.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '-'}
            </span>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default SettingsPage;
