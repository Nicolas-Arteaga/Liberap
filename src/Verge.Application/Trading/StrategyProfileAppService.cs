using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Volo.Abp;
using Volo.Abp.Application.Services;
using Volo.Abp.Domain.Repositories;
using Verge.Trading.DTOs;

namespace Verge.Trading;

public class StrategyProfileAppService : ApplicationService, IStrategyProfileAppService
{
    private readonly IRepository<StrategyProfile, Guid> _repo;

    public StrategyProfileAppService(IRepository<StrategyProfile, Guid> repo)
    {
        _repo = repo;
    }

    private static readonly Guid CloneProfileId = Guid.Parse("00000000-0000-0000-0000-000000000001");

    [HttpGet]
    public async Task<List<StrategyProfileDto>> GetListAsync()
    {
        var userId = CurrentUser.Id!.Value;
        var items = await _repo.GetListAsync(p => p.UserId == userId);
        var dtos = items.OrderBy(p => p.Name).Select(MapToDto).ToList();

        // Add virtual Standard Scalping profile at index 0
        dtos.Insert(0, new StrategyProfileDto
        {
            Id = Guid.Empty,
            UserId = userId,
            Name = "Standard Scalping",
            Description = "Estrategia predeterminada de la app (Scalping)",
            Color = "#3B82F6",
            IsActive = true
        });

        // Add virtual Scalping Clone profile (auto-clones Standard Scalping trades with -1 USDT SL)
        dtos.Insert(1, new StrategyProfileDto
        {
            Id = CloneProfileId,
            UserId = userId,
            Name = "Scalping Clone",
            Description = "Copia automática de Standard Scalping con SL de -1 USDT",
            Color = "#FF6B6B",
            IsActive = true
        });

        return dtos;
    }

    [HttpGet]
    public async Task<StrategyProfileDto> GetAsync(Guid id)
    {
        if (id == Guid.Empty)
        {
            return new StrategyProfileDto
            {
                Id = Guid.Empty,
                UserId = CurrentUser.Id!.Value,
                Name = "Standard Scalping",
                Description = "Estrategia predeterminada de la app (Scalping)",
                Color = "#3B82F6",
                IsActive = true
            };
        }

        if (id == CloneProfileId)
        {
            return new StrategyProfileDto
            {
                Id = CloneProfileId,
                UserId = CurrentUser.Id!.Value,
                Name = "Scalping Clone",
                Description = "Copia automática de Standard Scalping con SL de -1 USDT",
                Color = "#FF6B6B",
                IsActive = true
            };
        }
        var profile = await _repo.GetAsync(id);
        EnsureOwnership(profile);
        return MapToDto(profile);
    }

    [HttpPost]
    public async Task<StrategyProfileDto> CreateAsync(CreateUpdateStrategyProfileDto input)
    {
        var userId = CurrentUser.Id!.Value;
        var profile = new StrategyProfile(GuidGenerator.Create(), userId, input.Name);
        ApplyInput(profile, input);
        await _repo.InsertAsync(profile, autoSave: true);
        return MapToDto(profile);
    }

    [HttpPut]
    public async Task<StrategyProfileDto> UpdateAsync(Guid id, CreateUpdateStrategyProfileDto input)
    {
        if (id == Guid.Empty || id == CloneProfileId)
            throw new UserFriendlyException("No se puede editar una estrategia virtual del sistema.");
        var profile = await _repo.GetAsync(id);
        EnsureOwnership(profile);
        ApplyInput(profile, input);
        await _repo.UpdateAsync(profile, autoSave: true);
        return MapToDto(profile);
    }

    [HttpDelete]
    public async Task DeleteAsync(Guid id)
    {
        if (id == Guid.Empty || id == CloneProfileId)
            throw new UserFriendlyException("No se puede eliminar una estrategia virtual del sistema.");
        var profile = await _repo.GetAsync(id);
        EnsureOwnership(profile);
        await _repo.DeleteAsync(profile, autoSave: true);
    }

    [HttpPost]
    public async Task<StrategyProfileDto> ToggleActiveAsync(Guid id)
    {
        if (id == Guid.Empty) throw new UserFriendlyException("No se puede desactivar la estrategia predeterminada directamente.");
        var profile = await _repo.GetAsync(id);
        EnsureOwnership(profile);
        profile.IsActive = !profile.IsActive;
        await _repo.UpdateAsync(profile, autoSave: true);
        return MapToDto(profile);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────
    private void EnsureOwnership(StrategyProfile profile)
    {
        if (profile.UserId != CurrentUser.Id!.Value)
            throw new UserFriendlyException("You don't have permission to access this strategy profile.");
    }

    private static void ApplyInput(StrategyProfile p, CreateUpdateStrategyProfileDto i)
    {
        p.Name = i.Name;
        p.Description = i.Description;
        p.Color = i.Color;
        p.IsActive = i.IsActive;
        p.MinConfluenceScore = i.MinConfluenceScore;
        p.MinNexusConfidence = i.MinNexusConfidence;
        p.MaxRsiLong = i.MaxRsiLong;
        p.MinRsiShort = i.MinRsiShort;
        p.MaxMa7DistancePct = i.MaxMa7DistancePct;
        p.RequireMacdPositive = i.RequireMacdPositive;
        p.ExtremeRsiVeto = i.ExtremeRsiVeto;
        p.AllowedSources = i.AllowedSources;
        p.AllowLong = i.AllowLong;
        p.AllowShort = i.AllowShort;
        p.MarginPerTrade = i.MarginPerTrade;
        p.TpMultiplier = i.TpMultiplier;
        p.SlMultiplier = i.SlMultiplier;
        p.MinRR = i.MinRR;
        p.MaxOpenPositions = i.MaxOpenPositions;
        p.MaxTradeDurationCandles = i.MaxTradeDurationCandles;
        p.MaxEntrySlippagePct = i.MaxEntrySlippagePct;
        p.LseMaxEntrySlippagePct = i.LseMaxEntrySlippagePct;
        p.MinTpDistancePct = i.MinTpDistancePct;
        p.MinSlDistancePct = i.MinSlDistancePct;
        p.MinEstimatedRangePct = i.MinEstimatedRangePct;
        p.MaxNexusSignalAgeSeconds = i.MaxNexusSignalAgeSeconds;
        p.NexusMaxPriceDriftPct = i.NexusMaxPriceDriftPct;
    }

    private static StrategyProfileDto MapToDto(StrategyProfile p) => new()
    {
        Id = p.Id,
        UserId = p.UserId,
        Name = p.Name,
        Description = p.Description,
        Color = p.Color,
        IsActive = p.IsActive,
        MinConfluenceScore = p.MinConfluenceScore,
        MinNexusConfidence = p.MinNexusConfidence,
        MaxRsiLong = p.MaxRsiLong,
        MinRsiShort = p.MinRsiShort,
        MaxMa7DistancePct = p.MaxMa7DistancePct,
        RequireMacdPositive = p.RequireMacdPositive,
        ExtremeRsiVeto = p.ExtremeRsiVeto,
        AllowedSources = p.AllowedSources,
        AllowLong = p.AllowLong,
        AllowShort = p.AllowShort,
        MarginPerTrade = p.MarginPerTrade,
        TpMultiplier = p.TpMultiplier,
        SlMultiplier = p.SlMultiplier,
        MinRR = p.MinRR,
        MaxOpenPositions = p.MaxOpenPositions,
        MaxTradeDurationCandles = p.MaxTradeDurationCandles,
        MaxEntrySlippagePct = p.MaxEntrySlippagePct,
        LseMaxEntrySlippagePct = p.LseMaxEntrySlippagePct,
        MinTpDistancePct = p.MinTpDistancePct,
        MinSlDistancePct = p.MinSlDistancePct,
        MinEstimatedRangePct = p.MinEstimatedRangePct,
        MaxNexusSignalAgeSeconds = p.MaxNexusSignalAgeSeconds,
        NexusMaxPriceDriftPct = p.NexusMaxPriceDriftPct
    };
}
