import React from "react";

export interface TrainInfo {
  train_number: string;
  train_name: string;
  departure: string;
  arrival: string;
  duration: string;
  days?: string[];
  classes?: string[];
}

interface TrainResultCardProps {
  train: TrainInfo;
}

export default function TrainResultCard({ train }: TrainResultCardProps) {
  return (
    <div className="glass-card p-4 rounded-xl mb-3 animate-fade-in-up border border-[var(--border)] hover:border-indigo-500/50 transition-colors">
      <div className="flex justify-between items-start mb-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-lg text-white">
              {train.train_name}
            </h3>
            <span className="text-xs bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-500/30">
              {train.train_number}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between mt-4">
        <div className="text-center">
          <p className="text-xl font-bold text-white">{train.departure}</p>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
            Departs
          </p>
        </div>

        <div className="flex-1 px-4 relative flex flex-col items-center">
          <p className="text-[10px] text-[var(--text-muted)] mb-1">
            {train.duration}
          </p>
          <div className="w-full h-[1px] bg-gradient-to-r from-transparent via-indigo-400/50 to-transparent relative">
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px]">
              🚆
            </div>
          </div>
        </div>

        <div className="text-center">
          <p className="text-xl font-bold text-white">{train.arrival}</p>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
            Arrives
          </p>
        </div>
      </div>

      {(train.classes || train.days) && (
        <div className="mt-4 pt-3 border-t border-[var(--border)] flex justify-between items-center text-xs text-[var(--text-secondary)]">
          {train.classes && (
            <div className="flex gap-1">
              {train.classes.map((cls) => (
                <span
                  key={cls}
                  className="bg-[var(--bg-card)] px-1.5 py-0.5 rounded border border-[var(--border)]"
                >
                  {cls}
                </span>
              ))}
            </div>
          )}
          {train.days && (
            <div className="text-[10px] uppercase tracking-wide">
              Runs: {train.days.join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
