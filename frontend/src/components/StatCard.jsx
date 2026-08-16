import React from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';

/**
 * A dashboard summary tile: icon, label, big value, % change vs the
 * previous period, and an optional trend sparkline.
 */
const StatCard = ({ icon, iconBg, label, value, changePercent, sparkline, sparklineColor = '#6366F1' }) => {
  const hasChange = changePercent !== null && changePercent !== undefined;
  const isPositive = hasChange && changePercent >= 0;

  return (
    <div className="bg-white rounded-2xl shadow-sm p-5 flex flex-col">
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0`} style={{ backgroundColor: iconBg }}>
          {icon}
        </div>
        {hasChange && (
          <span className={`text-xs font-semibold flex items-center gap-0.5 ${isPositive ? 'text-emerald-600' : 'text-red-500'}`}>
            <svg className={`w-3 h-3 ${isPositive ? '' : 'rotate-180'}`} fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 17a.75.75 0 01-.75-.75V5.612L5.29 9.77a.75.75 0 01-1.08-1.04l5.25-5.5a.75.75 0 011.08 0l5.25 5.5a.75.75 0 11-1.08 1.04l-3.96-4.158V16.25A.75.75 0 0110 17z" clipRule="evenodd" />
            </svg>
            {Math.abs(changePercent).toFixed(1)}%
          </span>
        )}
      </div>

      <p className="text-gray-500 text-xs sm:text-sm font-medium">{label}</p>
      <p className="text-xl sm:text-2xl font-bold text-gray-900 mt-1 break-words">{value}</p>

      {hasChange && (
        <p className="text-xs text-gray-400 mt-1">vs previous period</p>
      )}

      {sparkline && sparkline.length >= 2 && (
        <div className="h-8 -mx-1 mt-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkline}>
              <Line type="monotone" dataKey="value" stroke={sparklineColor} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

export default StatCard;
