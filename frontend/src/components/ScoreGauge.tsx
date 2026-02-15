import React from 'react';

interface ScoreGaugeProps {
    score: number;
    size?: number;
}

export function ScoreGauge({ score }: ScoreGaugeProps) {
    // Determine color based on score
    let color = 'text-gray-400';
    if (score >= 75) color = 'text-emerald-500';
    else if (score >= 50) color = 'text-yellow-500';
    else if (score > 20) color = 'text-orange-500';
    else color = 'text-red-500';

    // Calculate circumference for SVG circle
    const radius = 30;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (score / 100) * circumference;

    return (
        <div className="relative flex items-center justify-center">
            <svg className="h-20 w-20 transform -rotate-90">
                {/* Background Circle */}
                <circle
                    className="text-muted/20"
                    strokeWidth="6"
                    stroke="currentColor"
                    fill="transparent"
                    r={radius}
                    cx="40"
                    cy="40"
                />
                {/* Progress Circle */}
                <circle
                    className={`${color} transition-all duration-1000 ease-out`}
                    strokeWidth="6"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                    stroke="currentColor"
                    fill="transparent"
                    r={radius}
                    cx="40"
                    cy="40"
                />
            </svg>
            <div className="absolute flex flex-col items-center justify-center top-0 bottom-0 left-0 right-0">
                <span className={`text-xl font-bold leading-none ${color}`}>{score}</span>
                <span className="text-[9px] text-muted-foreground uppercase leading-tight mt-0.5">Score</span>
            </div>
        </div>
    );
}
