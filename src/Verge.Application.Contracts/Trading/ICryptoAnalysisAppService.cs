using System;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public interface ICryptoAnalysisAppService : IApplicationService
{
    Task<SentimentAnalysisDto> GetSentimentForSymbolAsync(string symbol);
    Task<EnhancedAnalysisDto> GetEnhancedAnalysisAsync(Guid sessionId);
}
