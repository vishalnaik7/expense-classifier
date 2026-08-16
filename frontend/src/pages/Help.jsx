import React from 'react';
import Layout from '../components/Layout';

const FAQ = [
  { q: 'How do I upload a bank statement?', a: 'Go to Upload Statement in the sidebar, then drag in a CSV export from your bank (or tap to browse). We auto-detect the transaction table even if your bank adds extra rows above it, and skip anything you\'ve already uploaded.' },
  { q: 'Why is a transaction in the wrong category?', a: 'Open Transactions, click the category badge on any row, and pick a different one. You can also create your own categories under Categories.' },
  { q: 'How are budgets calculated?', a: 'Each budget tracks debit (spending) transactions in that category for the current calendar month against the monthly limit you set.' },
  { q: 'Is my data shared with anyone?', a: 'Your statements are parsed on our server and never shared. If a file needs AI-assisted parsing (rare, only when the standard parser can\'t read a layout), the file text is sent to Anthropic\'s API for that one request - see the Architecture doc for details.' },
];

const HelpPage = () => (
  <Layout>
    <div className="mb-6">
      <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Help & Support</h1>
      <p className="text-gray-500 mt-1 text-sm">Common questions about using the app</p>
    </div>

    <div className="max-w-2xl space-y-3">
      {FAQ.map((item, i) => (
        <div key={i} className="bg-white rounded-2xl shadow-sm p-5">
          <p className="font-semibold text-gray-900 text-sm mb-1">{item.q}</p>
          <p className="text-gray-500 text-sm leading-relaxed">{item.a}</p>
        </div>
      ))}
    </div>
  </Layout>
);

export default HelpPage;
